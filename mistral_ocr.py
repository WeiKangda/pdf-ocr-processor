from mistralai import Mistral
import os
import sys
import time
import json
from pdf2image import convert_from_path
from PIL import Image
import platform
from PyPDF2 import PdfReader, PdfWriter
import tempfile

# Configuration
INITIAL_DELAY = 2  # seconds
MAX_DELAY = 60  # maximum delay between retries in seconds
MAX_PAGES_PER_SPLIT = 300  # Maximum number of pages to process at once
MAX_FILE_SIZE_MB = 200  # Maximum file size in MB before splitting
MAX_PAGES = 1000  # Maximum number of pages before splitting

# Get API key from environment variable
# api_key = os.getenv('MISTRAL_API_KEY')
# Or simply paste your key here
# api_key = "Add your key here"
if not api_key:
    print("Error: MISTRAL_API_KEY environment variable is not set")
    print("Please set your Mistral AI API key using:")
    print("export MISTRAL_API_KEY='your-api-key-here'")
    sys.exit(1)

client = Mistral(api_key=api_key)

def get_poppler_path():
    """
    Get the poppler path based on the operating system.
    Returns the path if found, None otherwise.
    """
    if platform.system() == "Darwin":  # macOS
        possible_paths = [
            "/opt/homebrew/bin",  # Apple Silicon
            "/usr/local/bin",     # Intel
            "/opt/homebrew/opt/poppler/bin"  # Homebrew specific
        ]
    elif platform.system() == "Linux":
        possible_paths = ["/usr/bin"]
    elif platform.system() == "Windows":
        possible_paths = ["C:\\Program Files\\poppler-23.11.0\\Library\\bin"]
    else:
        return None

    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def extract_images_from_pdf(pdf_path, output_dir):
    """
    Extract and save images from PDF using coordinates from images.json.
    
    Args:
        pdf_path (str): Path to the PDF file
        output_dir (str): Directory where processed files are saved
    """
    try:
        # Load the images data
        images_file = os.path.join(output_dir, "images.json")
        if not os.path.exists(images_file):
            print(f"Error: images.json not found in {output_dir}")
            return
        
        with open(images_file, 'r', encoding='utf-8') as f:
            pages_data = json.load(f)
        
        # Get poppler path
        poppler_path = get_poppler_path()
        if not poppler_path:
            print("Error: Poppler not found. Please install poppler:")
            if platform.system() == "Darwin":
                print("  brew install poppler")
            elif platform.system() == "Linux":
                print("  sudo apt-get install poppler-utils")
            elif platform.system() == "Windows":
                print("  Download from: https://github.com/oschwartz10612/poppler-windows/releases/")
            return
        
        # Convert PDF pages to images
        try:
            pdf_images = convert_from_path(pdf_path, poppler_path=poppler_path)
        except Exception as e:
            print(f"Error converting PDF to images: {str(e)}")
            print("Please ensure poppler is installed and in PATH")
            return
        
        # Create images directory
        images_dir = os.path.join(output_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        # Process each page
        for page_data in pages_data:
            page_num = page_data['page_number'] - 1  # Convert to 0-based index
            if page_num >= len(pdf_images):
                print(f"Warning: Page {page_num + 1} not found in PDF")
                continue
                
            page_image = pdf_images[page_num]
            
            # Process each image on the page
            for img_data in page_data['images']:
                coords = img_data['coordinates']
                
                # Calculate the crop box
                left = coords['top_left_x']
                top = coords['top_left_y']
                right = coords['bottom_right_x']
                bottom = coords['bottom_right_y']
                
                # Crop the image
                cropped_image = page_image.crop((left, top, right, bottom))
                
                # Extract the image number from the ID
                image_id = img_data['id']
                # Remove any existing extensions and convert to consistent format
                base_name = image_id.split('.')[0]  # Remove any existing extension
                if '_' in base_name:
                    # Handle split PDF format (img_0)
                    num = base_name.split('_')[-1]
                    new_name = f"img-{num}.jpeg"
                else:
                    # Handle non-split PDF format (img-0.jpeg.png)
                    num = base_name.split('-')[-1]
                    new_name = f"img-{num}.jpeg"
                
                # Save the cropped image with consistent naming
                img_filename = os.path.join(images_dir, new_name)
                cropped_image.save(img_filename, format='JPEG')
                print(f"Saved image: {img_filename}")
                
    except Exception as e:
        print(f"Error extracting images: {str(e)}")

def save_processed_document(file_path, ocr_response):
    """
    Save the processed document's markdown and images.
    
    Args:
        file_path (str): Original PDF file path
        ocr_response: OCR response from Mistral API
    """
    # Get base filename without extension
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Create a separate folder for this document
    output_dir = os.path.join(os.path.dirname(file_path), base_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Create text directory
    text_dir = os.path.join(output_dir, "text")
    os.makedirs(text_dir, exist_ok=True)
    
    # Save markdown for each page
    for i, page in enumerate(ocr_response.pages):
        markdown_file = os.path.join(text_dir, f"page{i+1}.txt")
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(page.markdown)
    
    # Save page data including images and dimensions
    pages_data = []
    for i, page in enumerate(ocr_response.pages):
        page_info = {
            'page_number': i + 1,
            'dimensions': {
                'dpi': page.dimensions.dpi,
                'height': page.dimensions.height,
                'width': page.dimensions.width
            },
            'images': []
        }
        
        if hasattr(page, 'images') and page.images:
            for img in page.images:
                page_info['images'].append({
                    'id': img.id,
                    'coordinates': {
                        'top_left_x': img.top_left_x,
                        'top_left_y': img.top_left_y,
                        'bottom_right_x': img.bottom_right_x,
                        'bottom_right_y': img.bottom_right_y
                    }
                })
        
        pages_data.append(page_info)
    
    # Save the complete page data including images and dimensions
    images_file = os.path.join(output_dir, "images.json")
    with open(images_file, 'w', encoding='utf-8') as f:
        json.dump(pages_data, f, indent=2)
    
    # Extract and save the images
    extract_images_from_pdf(file_path, output_dir)

def retry_api_call(func, *args, **kwargs):
    attempt = 1
    delay = INITIAL_DELAY
    
    while True:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Attempt {attempt} failed: {str(e)}. Retrying in {delay} seconds...")
            time.sleep(delay)
            attempt += 1
            # Exponential backoff with a maximum delay
            delay = min(delay * 2, MAX_DELAY)

def is_fully_processed(file_path):
    """
    Check if a document has been fully processed.
    
    Args:
        file_path (str): Path to the PDF file
        
    Returns:
        bool: True if all pages have been processed, False otherwise
    """
    # Get the document's folder name
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_dir = os.path.join(os.path.dirname(file_path), base_name)
    
    if not os.path.exists(output_dir):
        return False
        
    # Check if we have at least one page file and the images.json file
    markdown_files = [f for f in os.listdir(output_dir) 
                     if f.startswith('page') and f.endswith('.txt')]
    images_file = os.path.join(output_dir, "images.json")
    
    return len(markdown_files) > 0 and os.path.exists(images_file)

def split_pdf(file_path):
    """
    Split a PDF into smaller parts if it's too large or has too many pages.
    
    Args:
        file_path (str): Path to the PDF file
        
    Returns:
        list: List of paths to split PDF files
    """
    try:
        # Check file size
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
        
        # Read the PDF
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        # Check if we need to split based on either size or page count
        if file_size_mb <= MAX_FILE_SIZE_MB and total_pages <= MAX_PAGES:
            return [file_path]
            
        if file_size_mb > MAX_FILE_SIZE_MB:
            print(f"File size ({file_size_mb:.2f}MB) exceeds {MAX_FILE_SIZE_MB}MB, splitting into parts...")
        if total_pages > MAX_PAGES:
            print(f"Page count ({total_pages}) exceeds {MAX_PAGES} pages, splitting into parts...")
        
        # Calculate number of splits needed based on both constraints
        splits_by_size = (total_pages + MAX_PAGES_PER_SPLIT - 1) // MAX_PAGES_PER_SPLIT
        splits_by_pages = (total_pages + MAX_PAGES - 1) // MAX_PAGES
        num_splits = max(splits_by_size, splits_by_pages)
        
        split_files = []
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Create temporary directory for split files
        temp_dir = tempfile.mkdtemp()
        
        # Split the PDF
        for i in range(num_splits):
            start_page = i * MAX_PAGES_PER_SPLIT
            end_page = min((i + 1) * MAX_PAGES_PER_SPLIT, total_pages)
            
            writer = PdfWriter()
            for page_num in range(start_page, end_page):
                writer.add_page(reader.pages[page_num])
                
            split_file = os.path.join(temp_dir, f"{base_name}_part{i+1}.pdf")
            with open(split_file, 'wb') as output_file:
                writer.write(output_file)
                
            split_files.append(split_file)
            
        return split_files
        
    except Exception as e:
        print(f"Error splitting PDF: {str(e)}")
        return [file_path]

def combine_results(results_list):
    """
    Combine results from multiple PDF splits.
    
    Args:
        results_list (list): List of OCR results from each split
        
    Returns:
        list: Combined pages with original OCR response structure
    """
    combined_pages = []
    total_pages = 0
    image_id_counter = 0  # Start from 0 to match the image numbering
    
    for result in results_list:
        if not result:
            continue
            
        for page in result.pages:
            # Create a page object with the same structure as the original OCR response
            class Page:
                def __init__(self, markdown, dimensions, images):
                    self.markdown = markdown
                    self.dimensions = dimensions
                    self.images = images
            
            class Dimensions:
                def __init__(self, dpi, height, width):
                    self.dpi = dpi
                    self.height = height
                    self.width = width
            
            # Create dimensions object
            dimensions = Dimensions(
                page.dimensions.dpi,
                page.dimensions.height,
                page.dimensions.width
            )
            
            # Create images list with updated IDs
            images = []
            if hasattr(page, 'images') and page.images:
                for img in page.images:
                    class Image:
                        def __init__(self, id, coordinates):
                            self.id = id
                            self.top_left_x = coordinates['top_left_x']
                            self.top_left_y = coordinates['top_left_y']
                            self.bottom_right_x = coordinates['bottom_right_x']
                            self.bottom_right_y = coordinates['bottom_right_y']
                    
                    # Generate a new image ID in the format img-{number}.jpeg
                    new_id = f"img-{image_id_counter}.jpeg"
                    image_id_counter += 1
                    
                    # Update the markdown text to use the new image ID
                    page.markdown = page.markdown.replace(img.id, new_id)
                    
                    images.append(Image(
                        new_id,
                        {
                            'top_left_x': img.top_left_x,
                            'top_left_y': img.top_left_y,
                            'bottom_right_x': img.bottom_right_x,
                            'bottom_right_y': img.bottom_right_y
                        }
                    ))
            
            # Create the page object
            page_obj = Page(page.markdown, dimensions, images)
            combined_pages.append(page_obj)
            total_pages += 1
    
    return combined_pages

def process_file_with_ocr(file_path):
    """
    Process a file using Mistral OCR.
    
    Args:
        file_path (str): Path to the file to process
        
    Returns:
        OCR response if successful, None if failed
    """
    try:
        # Split the PDF if needed
        split_files = split_pdf(file_path)
        if len(split_files) > 1:
            print(f"Splitting PDF into {len(split_files)} parts for processing")
        
        results = []
        for split_file in split_files:
            try:
                # Upload file
                uploaded_pdf = retry_api_call(
                    client.files.upload,
                    file={
                        "file_name": os.path.basename(split_file),
                        "content": open(split_file, "rb"),
                    },
                    purpose="ocr"
                )

                # Get signed URL
                signed_url = retry_api_call(
                    client.files.get_signed_url,
                    file_id=uploaded_pdf.id
                )

                # Process OCR
                ocr_response = retry_api_call(
                    client.ocr.process,
                    model="mistral-ocr-latest",
                    document={
                        "type": "document_url",
                        "document_url": signed_url.url,
                    }
                )
                
                results.append(ocr_response)
                
            except Exception as e:
                print(f"Error processing split file: {str(e)}")
                continue
                
            finally:
                # Clean up temporary split file
                if split_file != file_path:
                    try:
                        os.remove(split_file)
                    except:
                        pass
        
        if not results:
            return None
            
        # Combine results if PDF was split
        if len(results) > 1:
            combined_pages = combine_results(results)
            # Create a mock response with combined pages
            class MockResponse:
                def __init__(self, pages):
                    self.pages = pages
            return MockResponse(combined_pages)
            
        return results[0]
        
    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python mistral_ocr.py <pdf_file_or_folder_path>")
        sys.exit(1)
        
    input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} does not exist")
        sys.exit(1)
        
    # Process a single PDF file
    if os.path.isfile(input_path) and input_path.lower().endswith('.pdf'):
        if is_fully_processed(input_path):
            print(f"Skipping already processed file: {input_path}")
            sys.exit(0)
        print(f"Processing single PDF file: {input_path}")
        result = process_file_with_ocr(input_path)
        
        if result:
            print("Successfully processed the PDF file")
            save_processed_document(input_path, result)
        else:
            print("Failed to process the PDF file")
        sys.exit(0)
    
    # Process a folder of PDFs
    elif os.path.isdir(input_path):
        # Process all PDF files in the folder and its subfolders
        total_files = 0
        processed_files = 0
        skipped_files = 0
        failed_files = 0
        
        print(f"Starting to process PDF files in {input_path} and its subfolders...")
        
        for root, _, files in os.walk(input_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    total_files += 1
                    file_path = os.path.join(root, file)
                    print(f"\nProcessing file {total_files}: {file_path}")
                    
                    # Check if file has already been processed
                    if is_fully_processed(file_path):
                        print(f"Skipping already processed file: {file_path}")
                        skipped_files += 1
                        continue
                    
                    result = process_file_with_ocr(file_path)
                    
                    if result:
                        processed_files += 1
                        print(f"Successfully processed: {file_path}")
                        save_processed_document(file_path, result)
                    else:
                        failed_files += 1
                        print(f"Failed to process: {file_path}")
        
        print("\nProcessing Summary:")
        print(f"Total PDF files found: {total_files}")
        print(f"Successfully processed: {processed_files}")
        print(f"Skipped (already processed): {skipped_files}")
        print(f"Failed to process: {failed_files}")
    else:
        print(f"Error: {input_path} is neither a PDF file nor a directory")
        sys.exit(1)