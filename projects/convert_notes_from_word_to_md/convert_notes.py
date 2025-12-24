import os
from pathlib import Path
from docx import Document
import re
from datetime import datetime


def word_to_markdown(word_file_path, output_dir):
    """
    Convert a Word document to Markdown format.
    """
    doc = Document(word_file_path)
    markdown_content = []

    # Get the filename without extension for the title
    filename = Path(word_file_path).stem

    # Extract date and title from filename (assuming YYYY-MM-DD format)
    date_pattern = r"^(\d{4}-\d{2}-\d{2})\s*(.*)$"
    match = re.match(date_pattern, filename)

    if match:
        date_str = match.group(1)
        title = match.group(2).strip() if match.group(2) else "Meeting Notes"
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        title = filename

    # Add markdown header
    markdown_content.append(f"# {title}")
    markdown_content.append(f"**Date:** {date_str}\n")

    # Process each paragraph
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()

        if not text:
            continue

        # Check if it's a heading (based on style if available)
        if paragraph.style and paragraph.style.name:
            if "Heading 1" in paragraph.style.name:
                markdown_content.append(f"\n## {text}\n")
            elif "Heading 2" in paragraph.style.name:
                markdown_content.append(f"\n### {text}\n")
            elif "Heading 3" in paragraph.style.name:
                markdown_content.append(f"\n#### {text}\n")
            else:
                # Check for bullet points or numbered lists
                if paragraph.style.name.startswith("List"):
                    # Simple bullet point
                    markdown_content.append(f"- {text}")
                else:
                    # Regular paragraph
                    markdown_content.append(f"{text}\n")
        else:
            # If no style info, check for common patterns
            if text.startswith(("•", "·", "-", "*")):
                # Likely a bullet point
                clean_text = re.sub(r"^[•·\-*]\s*", "", text)
                markdown_content.append(f"- {clean_text}")
            elif re.match(r"^\d+[\.\)]\s", text):
                # Likely a numbered list
                markdown_content.append(text)
            else:
                # Regular paragraph
                markdown_content.append(f"{text}\n")

    # Save as markdown file
    output_filename = f"{filename}.md"
    output_path = Path(output_dir) / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown_content))

    return output_path


def batch_convert_folder(input_folder, output_folder):
    """
    Convert all Word documents in a folder to Markdown.
    """
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    # Create output directory if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all Word documents
    word_files = list(input_path.glob("*.docx")) + list(
        input_path.glob("*.doc")
    )

    if not word_files:
        print(f"No Word documents found in {input_folder}")
        return

    print(f"Found {len(word_files)} Word documents to convert")

    converted_count = 0
    failed_files = []

    for word_file in word_files:
        try:
            output_file = word_to_markdown(word_file, output_folder)
            print(f"✓ Converted: {word_file.name} → {output_file.name}")
            converted_count += 1
        except Exception as e:
            print(f"✗ Failed: {word_file.name} - Error: {str(e)}")
            failed_files.append(word_file.name)

    # Summary
    print(f"\n{'='*50}")
    print(f"Conversion Complete!")
    print(f"Successfully converted: {converted_count}/{len(word_files)} files")

    if failed_files:
        print(f"\nFailed files:")
        for file in failed_files:
            print(f"  - {file}")
        print(
            "\nTip: Failed files might need manual conversion or have complex formatting"
        )

    print(f"\nMarkdown files saved to: {output_folder}")


# Example usage
if __name__ == "__main__":
    # CONFIGURE THESE PATHS
    INPUT_FOLDER = (
        r"C:\Users\YourName\OneDrive\Meeting Notes"  # Your Word docs folder
    )
    OUTPUT_FOLDER = r"C:\Users\YourName\OneDrive\Meeting Notes MD"  # Where to save markdown files

    # Run the conversion
    batch_convert_folder(INPUT_FOLDER, OUTPUT_FOLDER)

    # Optional: Convert a single file
    # single_file = r"C:\path\to\your\document.docx"
    # word_to_markdown(single_file, OUTPUT_FOLDER)
