import os
import tempfile
import re
from typing import List, Dict, Optional, Tuple

class PdfToText:
    def __init__(self):
        """Initialize the PDF to text converter with PyMuPDF4LLM."""
        try:
            import pymupdf4llm
            import fitz  # PyMuPDF
            self.pymupdf4llm = pymupdf4llm
            self.fitz = fitz
        except ImportError:
            print("Installing required packages...")
            os.system("pip3 install pymupdf4llm PyMuPDF")
            try:
                import pymupdf4llm
                import fitz
                self.pymupdf4llm = pymupdf4llm
                self.fitz = fitz
            except ImportError:
                raise ImportError("Failed to install required packages: pymupdf4llm, PyMuPDF")
        
        # Initialize simple caption patterns
        self.CAPTION_PATTERNS = [
            r'(?i)(figure|fig\.?)\s*(\d+)[.:]\s*(.+?)(?=\n|\.|\s{2,}|$)',
            r'(?i)(table)\s*(\d+)[.:]\s*(.+?)(?=\n|\.|\s{2,}|$)',
            r'(?i)(diagram|schematic)\s*(\d+)[.:]\s*(.+?)(?=\n|\.|\s{2,}|$)'
        ]

    def convert(self, pdf_path: str) -> str:
        """Extract text content from a PDF file using PyMuPDF4LLM.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text content (plain text format)
        """
        try:
            # Use PyMuPDF4LLM for better text extraction
            markdown_text = self.pymupdf4llm.to_markdown(pdf_path)
            
            # Convert markdown to plain text (remove markdown formatting)
            plain_text = self._markdown_to_plain_text(markdown_text)
            
            if not plain_text.strip():
                return f"[No text content extracted from PDF: {pdf_path}]"
            
            return plain_text
            
        except Exception as e:
            return f"[Error reading PDF {pdf_path}: {str(e)}]"

    def convert_pages(self, pdf_path: str, from_page: int = 1, to_page: int = 0) -> str:
        """Extract text content from specific pages of a PDF file.

        Args:
            pdf_path: Path to the PDF file
            from_page: Starting page number (1-indexed, default: 1)
            to_page: Ending page number (1-indexed, default: 0 means last page)

        Returns:
            Extracted text content from specified pages
        """
        try:
            # Get total pages first
            doc = self.fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()

            # Validate page numbers
            if from_page < 1:
                from_page = 1
            if to_page <= 0 or to_page > total_pages:
                to_page = total_pages
            if from_page > to_page:
                return f"[Error: from_page ({from_page}) cannot be greater than to_page ({to_page})]"

            # Extract text from full document first, then filter pages
            full_markdown = self.pymupdf4llm.to_markdown(pdf_path)
            
            # Simple approach: extract pages by splitting on page markers
            # This is approximate since PyMuPDF4LLM doesn't have direct page range support
            lines = full_markdown.split('\n')
            page_content = []
            current_page = 1
            
            for line in lines:
                if current_page >= from_page and current_page <= to_page:
                    page_content.append(line)
                # Estimate page breaks (this is approximate)
                if len(line.strip()) == 0 and len(page_content) > 50:
                    current_page += 1
                    if current_page > to_page:
                        break
            
            result = '\n'.join(page_content)
            plain_text = self._markdown_to_plain_text(result)
            
            if not plain_text.strip():
                return f"[No text content extracted from PDF pages {from_page}-{to_page}: {pdf_path}]"
                
            return plain_text

        except Exception as e:
            return f"[Error reading PDF {pdf_path}: {str(e)}]"

    def convert_to_markdown(self, pdf_path: str, write_images: bool = False, 
                           output_dir: Optional[str] = None) -> str:
        """Convert PDF to Markdown format with enhanced formatting.

        Args:
            pdf_path: Path to the PDF file
            write_images: If True, extract and save images
            output_dir: Directory to save images (default: same as PDF)

        Returns:
            Markdown formatted text content
        """
        try:
            # Set up image output directory
            if write_images and output_dir:
                original_dir = os.getcwd()
                os.chdir(output_dir)
            
            # Convert to markdown with image extraction
            markdown_text = self.pymupdf4llm.to_markdown(pdf_path, write_images=write_images)
            
            # Restore directory if changed
            if write_images and output_dir:
                os.chdir(original_dir)
            
            return markdown_text
            
        except Exception as e:
            return f"[Error converting PDF to markdown {pdf_path}: {str(e)}]"

    def _get_image_position_in_text(self, pdf_path: str, page_num: int, image_index: int) -> Tuple[str, int]:
        """Get the approximate position of an image in the page text."""
        try:
            doc = self.fitz.open(pdf_path)
            page = doc[page_num]
            
            # Get all text blocks with positions
            text_blocks = page.get_text("dict")["blocks"]
            image_list = page.get_images()
            
            if image_index < len(image_list):
                # Get image rectangle
                img_rect = page.get_image_rects(image_list[image_index][0])[0] if page.get_image_rects(image_list[image_index][0]) else None
                
                if img_rect:
                    # Find text blocks before and after image position
                    full_text = page.get_text()
                    
                    # Simple approximation: find position based on y-coordinate
                    img_y = img_rect.y0
                    
                    # Get text blocks and sort by position
                    text_parts = []
                    for block in text_blocks:
                        if "lines" in block:
                            for line in block["lines"]:
                                line_y = line["bbox"][1]  # y0 coordinate
                                line_text = ""
                                for span in line["spans"]:
                                    line_text += span["text"]
                                if line_text.strip():
                                    text_parts.append((line_y, line_text.strip()))
                    
                    # Sort by y-coordinate
                    text_parts.sort(key=lambda x: x[0])
                    
                    # Find insertion point for image
                    insert_pos = 0
                    for i, (y_pos, text) in enumerate(text_parts):
                        if y_pos > img_y:
                            insert_pos = i
                            break
                    else:
                        insert_pos = len(text_parts)
                    
                    doc.close()
                    return full_text, insert_pos
            
            doc.close()
            return page.get_text(), 0
            
        except Exception:
            # Fallback to simple page text
            try:
                doc = self.fitz.open(pdf_path)
                page = doc[page_num]
                text = page.get_text()
                doc.close()
                return text, len(text.split('\n')) // 2  # Middle of page
            except Exception:
                return "", 0

    def _extract_surrounding_context(self, page_text: str, image_position: int, context_lines: int = 5) -> Dict[str, str]:
        """Extract text context around image position."""
        lines = page_text.split('\n')
        
        # Get lines around the image position
        start_idx = max(0, image_position - context_lines)
        end_idx = min(len(lines), image_position + context_lines)
        
        before_lines = lines[start_idx:image_position]
        after_lines = lines[image_position:end_idx]
        
        return {
            "before": '\n'.join(before_lines).strip(),
            "after": '\n'.join(after_lines).strip(),
            "full_context": '\n'.join(lines[start_idx:end_idx]).strip()
        }

    def _find_caption_in_context(self, context: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Find figure/table captions in the surrounding context."""
        # Check both before and after text for captions
        search_text = context["before"] + "\n" + context["after"]
        
        for pattern in self.CAPTION_PATTERNS:
            matches = re.finditer(pattern, search_text)
            for match in matches:
                return {
                    "type": match.group(1).lower(),
                    "number": match.group(2) if len(match.groups()) > 1 else "",
                    "description": match.group(3).strip() if len(match.groups()) > 2 else ""
                }
        return None

    def _generate_simple_metadata(self, pdf_path: str, page_num: int, image_index: int, image_size: Tuple[int, int]) -> Dict[str, any]:
        """Generate metadata based on actual surrounding text context."""
        # Get image position and page text
        page_text, image_position = self._get_image_position_in_text(pdf_path, page_num, image_index)
        
        # Extract surrounding context
        context = self._extract_surrounding_context(page_text, image_position, context_lines=5)
        
        # Find caption in context
        caption = self._find_caption_in_context(context)
        
        # Generate description from available information
        description_parts = []
        
        if caption and caption.get("description"):
            description_parts.append(f"{caption['type'].title()} {caption.get('number', '')}: {caption['description']}")
        
        # Add context clues from surrounding text
        context_text = context["full_context"].lower()
        
        # Simple keyword extraction from actual context
        technical_terms = []
        common_terms = ["pin", "circuit", "diagram", "table", "graph", "chart", "block", "schematic", 
                       "timing", "waveform", "package", "footprint", "register", "memory", "application"]
        
        for term in common_terms:
            if term in context_text:
                technical_terms.append(term)
        
        if not description_parts and technical_terms:
            description_parts.append(f"Technical diagram related to {', '.join(technical_terms[:3])}")
        
        if not description_parts:
            description_parts.append("Technical diagram or illustration")
        
        # Calculate confidence based on available information
        confidence = 0.0
        if caption:
            confidence += 0.6  # High confidence if we have a caption
        if technical_terms:
            confidence += 0.3  # Medium confidence if we have technical context
        if len(context["full_context"]) > 50:
            confidence += 0.1  # Small boost if we have substantial context
        
        confidence = min(confidence, 1.0)
        
        return {
            "description": " ".join(description_parts),
            "caption": caption,
            "surrounding_text": {
                "before": context["before"][:200] + "..." if len(context["before"]) > 200 else context["before"],
                "after": context["after"][:200] + "..." if len(context["after"]) > 200 else context["after"]
            },
            "confidence": confidence
        }

    def extract_images(self, pdf_path: str, output_dir: Optional[str] = None) -> List[Dict[str, any]]:
        """Extract all images from PDF file using PyMuPDF4LLM.

        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory to save images (default: temp directory)

        Returns:
            List of dictionaries containing image information with contextual metadata
        """
        return self._extract_images_pymupdf4llm(pdf_path, output_dir)

    def _extract_images_pymupdf4llm(self, pdf_path: str, output_dir: Optional[str] = None) -> List[Dict[str, any]]:
        """Extract images using PyMuPDF4LLM's built-in extraction."""
        try:
            if output_dir is None:
                output_dir = tempfile.mkdtemp()
            
            os.makedirs(output_dir, exist_ok=True)
            
            # Use PyMuPDF4LLM to extract images
            original_dir = os.getcwd()
            os.chdir(output_dir)
            
            try:
                # Extract markdown with images - this saves images to current directory
                markdown_text = self.pymupdf4llm.to_markdown(pdf_path, write_images=True)
                
                # Get list of extracted image files
                image_files = [f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                image_files.sort()  # Sort for consistent ordering
                
                images_info = []
                
                for i, filename in enumerate(image_files):
                    img_path = os.path.join(output_dir, filename)
                    
                    # Parse filename to get page info (PyMuPDF4LLM format: filename-page-index.ext)
                    try:
                        # Extract page number from filename pattern
                        # PyMuPDF4LLM typically creates: "originalname.pdf-page-imgindex.png"
                        parts = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').split('-')
                        
                        # Find numeric parts that could be page numbers
                        page_num = 0
                        img_index = i
                        
                        for j, part in enumerate(parts):
                            if part.isdigit():
                                if j == len(parts) - 2:  # Second to last number is usually page
                                    page_num = int(part)
                                elif j == len(parts) - 1:  # Last number is usually image index
                                    img_index = int(part)
                        
                        # If we didn't find page number, try to extract from position in list
                        if page_num == 0:
                            # Estimate page based on image index (rough approximation)
                            page_num = (i // 3) + 1  # Assume ~3 images per page on average
                            
                    except (ValueError, IndexError):
                        page_num = (i // 3) + 1  # Fallback: estimate page
                        img_index = i
                    
                    # Get image size
                    try:
                        from PIL import Image
                        with Image.open(img_path) as img:
                            width, height = img.size
                    except Exception:
                        width, height = 0, 0
                    
                    # Generate contextual metadata
                    metadata = self._generate_simple_metadata(pdf_path, page_num, img_index, (width, height))
                    
                    # Store image info
                    images_info.append({
                        "page": page_num + 1,
                        "filename": filename,
                        "path": img_path,
                        "metadata": metadata
                    })
                
                return images_info
                
            finally:
                os.chdir(original_dir)
            
        except Exception as e:
            return [{"error": f"Error extracting images with PyMuPDF4LLM: {str(e)}"}]


    def get_pdf_info(self, pdf_path: str) -> Dict[str, any]:
        """Get PDF document information.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary containing PDF metadata and statistics
        """
        try:
            doc = self.fitz.open(pdf_path)
            
            # Get metadata
            metadata = doc.metadata
            
            # Get page count and text statistics
            page_count = len(doc)
            total_chars = 0
            
            # Sample first few pages for text density estimation
            sample_pages = min(3, page_count)
            for i in range(sample_pages):
                page = doc[i]
                text = page.get_text()
                total_chars += len(text)
            
            # Estimate total characters
            if sample_pages > 0:
                avg_chars_per_page = total_chars / sample_pages
                estimated_total_chars = int(avg_chars_per_page * page_count)
            else:
                estimated_total_chars = 0
            
            doc.close()
            
            return {
                "title": metadata.get("title", "Unknown"),
                "author": metadata.get("author", "Unknown"),
                "subject": metadata.get("subject", ""),
                "creator": metadata.get("creator", "Unknown"),
                "producer": metadata.get("producer", "Unknown"),
                "creation_date": metadata.get("creationDate", "Unknown"),
                "modification_date": metadata.get("modDate", "Unknown"),
                "page_count": page_count,
                "estimated_characters": estimated_total_chars,
                "file_size": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            }
            
        except Exception as e:
            return {"error": f"Error getting PDF info: {str(e)}"}

    def _markdown_to_plain_text(self, markdown_text: str) -> str:
        """Convert markdown text to plain text by removing formatting.

        Args:
            markdown_text: Markdown formatted text

        Returns:
            Plain text with markdown formatting removed
        """
        import re
        
        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', markdown_text, flags=re.MULTILINE)
        
        # Remove bold and italic formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'__([^_]+)__', r'\1', text)      # Bold underscore
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Italic underscore
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Remove code blocks and inline code
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        return text.strip()
