import os
import argparse
import shutil
import base64
import re
import subprocess
import glob
import time
import logging
import chardet
import hashlib
import pandas as pd
from openpyxl import load_workbook
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# List potential drives to search
drives = ["C:", "D:"]  # Add more if needed

jenkins_paths = []

# Search for Jenkins config paths in all possible drives
for drive in drives:
    search_path = os.path.join(drive, "JS", "workspace", "**", "config", "Jenkins")
    jenkins_paths.extend(glob.glob(search_path, recursive=True))

# If no Jenkins paths found, dynamically search for the SWTest-related folder in all drives
if not jenkins_paths:
    found_fallback = False
    for drive in drives:
        workspace_base = os.path.join(drive, "JS", "workspace")
        if os.path.exists(workspace_base):
            possible_folders = glob.glob(os.path.join(workspace_base, "*"))  # List all folders inside workspace

            swtest_folders = [
                folder for folder in possible_folders if "SWTest" in os.path.basename(folder)
            ]  # Filter potential SWTest folders dynamically

            if swtest_folders:
                fallback_path = os.path.join(swtest_folders[0], "config", "Jenkins")  # Pick the first matching folder
                jenkins_paths.append(fallback_path)
                found_fallback = True
                break  # Stop searching once a valid fallback is found

    if not found_fallback:
        logging.warning("No SWTest-related folder found in any workspace. Jenkins paths will be empty.")

# Default source paths
DEFAULT_SOURCE_PATHS = jenkins_paths + [
    r"C:\JS\ws\develop\sw\Release",
    r"C:\JS\CT_Server_Standard_files_Continous_Testing\images",
    r"C:\JS\CT_Server_Standard_files_Continous_Testing\python",
    os.path.join(os.getcwd(), "images"),
]

logging.info(f"Using Jenkins paths: {jenkins_paths}")
logging.info(f"Final DEFAULT_SOURCE_PATHS: {DEFAULT_SOURCE_PATHS}")

# Default destination directory (current working directory)
DEFAULT_DESTINATION_PATH = os.getcwd()
EXCEL_REPORT_PATH = os.path.join(DEFAULT_DESTINATION_PATH, "Software_Test_Report.xlsx")
HTML_REPORT_PATH = os.path.join(DEFAULT_DESTINATION_PATH, "Software_Test_Report.html")

def find_html_files_recursive(directory, matched_files=None):
    """Recursively finds all .html files in the given directory and logs the count."""
    
    if matched_files is None:
        matched_files = set()  # Use a set to store unique file paths

    if not os.path.exists(directory):
        logging.warning(f"Skipping non-existent path: {directory}")
        return matched_files  # Return existing found files

    try:
        logging.info(f"Searching for HTML files in: {directory}")

        for entry in os.scandir(directory):  # Efficient directory iteration
            #if entry.is_file() and entry.name.lower().endswith(".html") or entry.name.lower().endswith(".txt"):
            if entry.is_file() and entry.name.lower().endswith(".html"):
                matched_files.add(os.path.normpath(entry.path))  # Normalize path
            elif entry.is_dir():  # Recurse into subdirectory
                find_html_files_recursive(entry.path, matched_files)

    except Exception as e:
        logging.error(f"Error searching in {directory}: {e}")

    return matched_files

# Wrapper function to process multiple source paths
def find_html_files(source_paths):
    """Handles multiple source directories and returns all found HTML files."""
    
    if isinstance(source_paths, str):  
        logging.error("Error: source_paths should be a list, not a string!")
        return []

    all_matched_files = set()
    
    for path in source_paths:
        all_matched_files.update(find_html_files_recursive(path))  # Call recursive function

    logging.info(f"Total unique HTML files found: {len(all_matched_files)}")
    
    return list(all_matched_files)  # Convert set to list


def extract_summary_data(soup):
    """Extracts executed, passed, and failed test case counts from the summary table."""
    executed_count, pass_count, fail_count = 0, 0, 0
    
    overview_table = soup.find("table", class_="OverviewTable")
    if overview_table:
        rows = overview_table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            row_text = [cell.get_text(strip=True) for cell in cells]
            if "Executed test cases" in row_text[0]:
                executed_count = int(row_text[1])
            elif "Test cases passed" in row_text[0]:
                pass_count = int(row_text[1])
            elif "Test cases failed" in row_text[0]:
                fail_count = int(row_text[1])
    
    return executed_count, pass_count, fail_count

def extract_failed_tests(soup):
    """Extracts failed test cases from the report using BeautifulSoup."""
    failed_tests = ""
    failure_sections = soup.find_all("table", class_="FailureTable")  # Ensure correct class
    
    for section in failure_sections:
        failed_tests += str(section)

    return failed_tests if failed_tests else "<p>No failed tests found.</p>"

def extract_keyword_from_tables(soup, keyword):
    """Extracts table rows that contain the given keyword."""
    keyword_lower = keyword.lower()
    extracted_rows = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if any(keyword_lower in cell.get_text(strip=True).lower() for cell in cells):
                extracted_rows.append(str(row))

    return f"<table border='1'>{''.join(extracted_rows)}</table>" if extracted_rows else "<p>No matching keyword data found.</p>"

def append_to_excel(test_name, pass_count, fail_count):
    """Appends test data to an Excel sheet while ensuring correct headers exist."""
    sheet_name = "Summary"

    # Ensure the Excel file exists and create it if necessary
    if not os.path.exists(EXCEL_REPORT_PATH):
        df = pd.DataFrame(columns=["Test Name", "Passed", "Failed"])
        df.to_excel(EXCEL_REPORT_PATH, index=False, sheet_name=sheet_name)

    with pd.ExcelWriter(EXCEL_REPORT_PATH, engine="openpyxl", mode="w", if_sheet_exists="new") as writer:
        book = load_workbook(EXCEL_REPORT_PATH)

        if sheet_name in book.sheetnames:
            df = pd.read_excel(EXCEL_REPORT_PATH, sheet_name=sheet_name)

            # Ensure Passed and Failed columns are numeric
            df["Passed"] = pd.to_numeric(df["Passed"], errors="coerce").fillna(0)
            df["Failed"] = pd.to_numeric(df["Failed"], errors="coerce").fillna(0)

            new_data = pd.DataFrame({"Test Name": [test_name], "Passed": [pass_count], "Failed": [fail_count]})
            df = pd.concat([df, new_data]).drop_duplicates(subset=["Test Name"], keep="last")

            df.to_excel(writer, sheet_name=sheet_name, index=False)

        else:
            df = pd.DataFrame({"Test Name": [test_name], "Passed": [pass_count], "Failed": [fail_count]})
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    logging.info(f"Data appended to {EXCEL_REPORT_PATH} under sheet '{sheet_name}'")

def generate_graph():
    """Generates a graph showing pass/fail test trends and a consolidated summary pie chart."""
    try:
        df = pd.read_excel(EXCEL_REPORT_PATH, sheet_name="Summary")
    
        # Convert columns to numeric
        df["Passed"] = pd.to_numeric(df["Passed"], errors="coerce").fillna(0)
        df["Failed"] = pd.to_numeric(df["Failed"], errors="coerce").fillna(0)

        # Check if there's valid data to plot
        if df[["Passed", "Failed"]].sum().sum() == 0:
            logging.warning("No valid test data available. Skipping graph generation.")
            return

        # Create a bar chart for individual test pass/fail trends
        plt.figure(figsize=(12, 6))
        df[['Test Name', 'Passed', 'Failed']].plot(kind='bar', x='Test Name', stacked=True, color=['green', 'red'])
        plt.title("Test Pass/Fail Trends")
        plt.ylabel("Count")
        plt.xticks(rotation=75, ha="right", fontsize=8)
        plt.tight_layout()
        plt.savefig(os.path.join(DEFAULT_DESTINATION_PATH, "Test_Results_Graph.png"))
        logging.info("Test Pass/Fail Trends graph updated and saved.")

        # Create a pie chart for the consolidated summary report
        total_passed = df['Passed'].sum()
        total_failed = df['Failed'].sum()

        plt.figure(figsize=(6, 6))
        plt.pie(
            [total_passed, total_failed], 
            labels=['Passed', 'Failed'], 
            autopct='%1.1f%%', 
            colors=['green', 'red'], 
            startangle=90, 
            wedgeprops={'edgecolor': 'black'}
        )
        plt.title("Consolidated Summary Report")
        plt.savefig(os.path.join(DEFAULT_DESTINATION_PATH, "Consolidated_Summary_Report.png"))
        logging.info("Consolidated Summary Report pie chart updated and saved.")

    except Exception as e:
        logging.error(f"Error generating graph: {e}")

def minify_html(html_content):
    """Removes excessive whitespace while preserving structure."""
    # Remove spaces between HTML tags
    html_content = re.sub(r">\s+<", "><", html_content)
    
    # Reduce multiple spaces to a single space
    html_content = re.sub(r"\s{2,}", " ", html_content)
    
    return html_content.strip()

def remove_empty_sections(html):
    """Removes empty <details> and <div> sections."""
    html = re.sub(r"<details>\s*<summary>.*?</summary>\s*<div>\s*</div>\s*</details>", "", html, flags=re.DOTALL)
    html = re.sub(r"<pre>\s*</pre>", "", html, flags=re.DOTALL)
    return html

def generate_html_report(html_files, source_paths, destination_path, keyword):
    """Generates a structured, navigable HTML report with a fixed left navigation column and toggle functionality."""
    
    try:
        logging.info("Starting report generation...")

        # Copy files and get copied file list
        text_content, image_tags, copied_files = copy_and_embed_files(source_paths, destination_path)

        seen_files = set()
        statistics_table_html = ""
        failed_tests_html = ""
        keyword_table_rows_html = ""
        navigation_links = ""
        report_sections_html = ""

        for index, html_file in enumerate(html_files):
            if html_file in seen_files:
                continue  # Skip duplicate files

            try:
                logging.info(f"Processing HTML file: {html_file}")
                with open(html_file, 'r', encoding='utf-8') as file:
                    soup = BeautifulSoup(file, 'html.parser')

                    file_title = os.path.basename(html_file).replace("_", " ").replace(".html", "").title()
                    section_id = f"section-{index}"

                    # Add navigation link to sidebar
                    navigation_links += f'<li><a href="javascript:void(0);" onclick="toggleSection(\'{section_id}\')">{file_title}</a></li>'

                    # Create a <details> section for each report file
                    section_content = f"""
                    <details id="{section_id}">
                        <summary>{file_title}</summary>
                        {extract_statistics_table(soup)}
                        {extract_failed_tests(soup)}
                        {extract_keyword_from_tables(soup, keyword)}
                    </details>
                    """

                    report_sections_html += section_content  # Add to report body
                    seen_files.add(html_file)

            except Exception as e:
                logging.error(f"Error processing {html_file}: {e}")

        logging.info(f"Total HTML reports added: {len(seen_files)}")

        # **Final Report Template with Fixed Navigation and JavaScript for Toggle**
        html_template = f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Software Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; display: flex; }}
                .sidebar {{
                    width: 250px;
                    height: 100vh;
                    position: fixed;
                    background-color: #333;
                    color: white;
                    padding: 20px;
                    overflow-y: auto;
                }}
                .sidebar h2 {{ text-align: center; font-size: 18px; }}
                .sidebar ul {{
                    list-style-type: none;
                    padding: 0;
                }}
                .sidebar ul li {{
                    padding: 8px;
                    border-bottom: 1px solid #555;
                }}
                .sidebar ul li a {{
                    text-decoration: none;
                    color: white;
                    display: block;
                }}
                .sidebar ul li a:hover {{
                    background-color: #555;
                }}
                .content {{
                    margin-left: 270px;
                    padding: 20px;
                    width: calc(100% - 270px);
                }}
                h1, h2, h3 {{ margin: 10px 0; }}
                pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 5px 0; }}
                details {{ margin-bottom: 5px; }}
                summary {{ padding: 5px; background: #eee; border-radius: 3px; cursor: pointer; }}
            </style>
            <script>
                function toggleSection(id) {{
                    var section = document.getElementById(id);
                    if (section) {{
                        section.open = !section.open;
                        section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    }}
                }}
            </script>
        </head>
        <body>
        
            <div class="sidebar">
                <h2>Navigation</h2>
                <ul>
                    <li><a href="javascript:void(0);" onclick="toggleSection('logs')">Logs & Info</a></li>
                    <li><a href="javascript:void(0);" onclick="toggleSection('images')">Embedded Images</a></li>
                    <li><a href="javascript:void(0);" onclick="toggleSection('copied-files')">Copied Files</a></li>
                    {navigation_links}
                </ul>
            </div>

            <div class="content">
                <h1>Software Test Report</h1>

                <details id="logs">
                    <summary>Logs & Additional Information</summary>
                    <div>{text_content if text_content else "<p>No logs available</p>"}</div>
                </details>

                <details id="images">
                    <summary>Embedded Images</summary>
                    <div>{image_tags if image_tags else "<p>No images found</p>"}</div>
                </details>

                <details id="copied-files">
                    <summary>Copied Files</summary>
                    <ul>
                        {''.join(f"<li>{os.path.basename(file)}</li>" for file in copied_files) if copied_files else "<p>No copied files</p>"}
                    </ul>
                </details>

                {report_sections_html} <!-- Inject report sections -->

            </div>

        </body>
        </html>"""

        # **Minify & Remove Empty Sections Before Saving**
        html_template = minify_html(remove_empty_sections(html_template))

        output_path = os.path.join(destination_path, "Software_Test_Report.html")

        with open(output_path, "w", encoding="utf-8") as html_file:
            html_file.write(html_template)

        logging.info(f"Report successfully generated at {output_path}")

    except Exception as e:
        logging.critical(f"Unexpected error generating the report: {e}")

def extract_results_table(soup):
    results_table = []
    start_write = False

    for div in soup.find_all('div'):
        # Start 
        if "Results" in div.get_text():
            start_write = True

        # Stop 
        if "Test Configuration Information" in div.get_text() and start_write:
            start_write = False

        # look for the table containing the results
        if start_write and div.find('table'):
            table = div.find('table')
            for row in table.find_all('tr'):
                columns = [col.get_text(strip=True) for col in row.find_all('td')]
                
                # start adding rows once the first column is "1"
                if len(columns) > 0 and columns[0] == "1":
                    if len(columns) >= 3 and columns[2].lower() == "fail": 
                        results_table.append(columns[:3]) 

                # keep capturing only 'fail' rows
                elif len(results_table) > 0 and len(columns) >= 3 and columns[2].lower() == "fail":
                    results_table.append(columns[:3])  
    
    return results_table
def extract_keyword_table(soup, keyword):
    """Extracts tables related to the specific keywords from the HTML report."""
    keyword_tables = {keyword: [] for keyword in keywords}
    found_keyword_section = {keyword: False for keyword in keywords}
    parsed_tables = {keyword: False for keyword in keywords} 

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for row in rows:
            text = row.get_text(strip=True)

            for keyword in keywords:
                # check both conditions 
                if (f"CAN signal '{keyword}'" in text or f"_22{keyword}" in text) and not parsed_tables[keyword]:  
                    found_keyword_section[keyword] = True

                if found_keyword_section[keyword] and "Check of expected values" in text:
                    # Look for the next table
                    response_table = row.find_next('table', class_='InfoTableExpand')
                    if response_table:
                        # Extract data from the found table
                        for data_row in response_table.find_all('tr'):
                            columns = [col.get_text(strip=True) for col in data_row.find_all('td')]
                            if columns:  
                                keyword_tables[keyword].append(columns)
                        # Mark this keyword's table as parsed
                        parsed_tables[keyword] = True
                    # Stop after the first match for this keyword
                    found_keyword_section[keyword] = False

    return keyword_tables

def extract_statistics_table(soup):
    """Extracts the Statistics table from the HTML content."""
    statistics_table = []
    start_write = False

    for div in soup.find_all('div'):
        if "Statistics" in div.get_text():
            start_write = True
        
        if "Warnings occured during test execution." in div.get_text() and start_write:
            start_write = False
        
        if start_write and div.find('table'):
            table = div.find('table')
            for row in table.find_all('tr'):
                columns = row.find_all('td')
                statistics_table.append([col.get_text(strip=True) for col in columns])
    
    return statistics_table

def extract_statistics_table(soup):
    # Locate the statistics table (modify class or ID if needed)
    statistics_table = soup.find("table", class_="OverviewTable")  # Adjust class if necessary

    if statistics_table:
        return f"<h2>Test Statistics</h2>{str(statistics_table)}"
    else:
        return "<p><b>No statistics table found in the report.</b></p>"

def extract_failed_tests(soup):
    failed_tests = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            for cell in cells:
                if "fail" in cell.get_text(strip=True).lower():
                    failed_tests.append(str(row))  # Keep row as-is without styling
                    break  # Stop checking other cells in this row

    return f"<h2>Failed Tests Summary</h2><table>{''.join(failed_tests)}</table>" if failed_tests else "<p><b>No failed tests found.</b></p>"

def extract_keyword_from_tables(soup, keyword):
    """Extracts and formats table rows containing the given keyword from an HTML soup object."""
    keyword_lower = keyword.lower()
    extracted_rows = []

    # Iterate over all tables in the soup
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            # Check if any cell in the row contains the keyword
            if any(keyword_lower in cell.get_text(strip=True).lower() for cell in cells):
                extracted_rows.append(str(row))

    # Format the output neatly without table borders
    if extracted_rows:
        table_html = "<table>\n" + "\n".join(extracted_rows) + "\n</table>"
        return f"<h2>Table Data Matching Keyword: '{keyword}'</h2>\n{table_html}"
    else:
        return f"<p><b>No table rows found containing keyword: '{keyword}'</b></p>"

def extract_overview_table(soup):
    """Extracts executed, pass, and fail count from the 'OverviewTable'."""
    global pass_count, fail_count, executed_count

    overview_table = soup.find("table", class_="Statistics")
    if not overview_table:
        return "<p><b>OverviewTable not found in the report.</b></p>"

    rows = overview_table.find_all("tr")
    extracted_table = "<h2>Test Summary</h2><table border='1'>"

    for row in rows:
        cells = row.find_all("td")
        row_text = [cell.get_text(strip=True) for cell in cells]

        if "Executed test cases" in row_text[0]:
            executed_count = int(row_text[1])
        elif "Test cases passed" in row_text[0]:
            pass_count = int(row_text[1])
        elif "Test cases failed" in row_text[0]:
            fail_count = int(row_text[1])

        extracted_table += f"<tr>{''.join(f'<td>{cell}</td>' for cell in row_text)}</tr>"

    extracted_table += "</table>"
    return extracted_table

# Allowed file extensions (only images & text files)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "txt", "html"}

def detect_encoding(file_path):
    """Detects file encoding before reading."""
    with open(file_path, "rb") as f:
        raw_data = f.read(4096)  # Read the first 4KB for detection
        result = chardet.detect(raw_data)
        return result["encoding"] if result["encoding"] else "utf-8"

def get_unique_filename(dest_dir, filename):
    """Ensures a unique filename by appending a number if it already exists."""
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename

    while os.path.exists(os.path.join(dest_dir, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1

    return new_filename

def get_file_hash(file_path):
    """Generate a hash for a file to detect duplicates."""
    hasher = hashlib.md5()  # Using MD5 for simplicity; SHA256 can also be used.
    with open(file_path, "rb") as f:
        hasher.update(f.read())  # Read and hash the entire file
    return hasher.hexdigest()

def copy_and_embed_files(source_paths, destination_path, delete_after_embedding=True):
    """Copies and embeds ONLY images and text files, renaming them if necessary to avoid overwriting.
    Prevents duplicate embedding by checking file hashes.
    """
    
    image_tags = ""
    text_content = ""
    image_count = 0
    text_count = 0
    copied_files = []  # List of successfully copied files
    embedded_hashes = set()  # Track unique files by content hash

    if not os.path.exists(destination_path):
        os.makedirs(destination_path)

    for source_path in source_paths:
        if not os.path.exists(source_path):
            logging.warning(f"Skipping non-existent path: {source_path}")
            continue

        for root, _, files in os.walk(source_path):
            for filename in files:
                file_ext = filename.lower().split(".")[-1]

                # **Only process files with allowed extensions**
                if file_ext not in ALLOWED_EXTENSIONS:
                    logging.info(f"Skipping unsupported file: {filename}")
                    continue

                src_file = os.path.join(root, filename)

                # Preserve folder structure
                relative_path = os.path.relpath(root, source_path)
                dest_dir = os.path.join(destination_path, relative_path)
                os.makedirs(dest_dir, exist_ok=True)

                # Get a unique filename to prevent overwriting
                unique_filename = get_unique_filename(dest_dir, filename)
                dest_file = os.path.join(dest_dir, unique_filename)

                try:
                    shutil.copy2(src_file, dest_file)  # Copy file

                    # **Verify File Exists After Copying**
                    if os.path.exists(dest_file):
                        file_hash = get_file_hash(dest_file)  # Compute hash

                        if file_hash in embedded_hashes:
                            logging.info(f"Skipping duplicate file: {unique_filename}")
                            continue  # Don't embed duplicate content
                        
                        embedded_hashes.add(file_hash)  # Mark file as embedded
                        copied_files.append(dest_file)  # Store successfully copied file

                        # Embed images into report
                        if file_ext in ["png", "jpg", "jpeg", "gif"]:
                            with open(dest_file, "rb") as img_file:
                                base64_str = base64.b64encode(img_file.read()).decode('utf-8')
                                mime_type = f"image/{file_ext}"
                                image_tags += f'<img src="data:{mime_type};base64,{base64_str}" alt="{unique_filename}" style="max-width: 100%; display: block; margin: 10px 0;"><br>\n'
                            image_count += 1

                        # Embed text into report
                        elif file_ext in ["txt", "html"]:
                            encoding = detect_encoding(dest_file)
                            with open(dest_file, "r", encoding=encoding, errors="replace") as txt_file:
                                text_content += f"<h3>{unique_filename}</h3><pre>{txt_file.read()}</pre><br>"
                            text_count += 1

                except Exception as e:
                    logging.error(f"Failed to copy {src_file} to {dest_file}: {e}")

    logging.info(f"Total text/HTML files copied: {text_count}")
    logging.info(f"Total image files copied: {image_count}")
    logging.info(f"Total successfully copied files: {len(copied_files)}")

    # **Delete copied files if flag is set**
    if delete_after_embedding:
        for file_path in copied_files:
            try:
                os.remove(file_path)
                logging.info(f"Deleted file: {file_path}")
            except Exception as e:
                logging.error(f"Failed to delete {file_path}: {e}")

    return text_content, image_tags, copied_files  # Return copied file list


def getCPULoadResults():
    command_args = ["python", "CPU_Load_Graph_Parser.py"]
    try:
        result = subprocess.run(command_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(f"Error occurred:\n{result.stderr}")
        else:
            print("CPU Load processing complete. Now cleaning workspaces...")

    except Exception as e:
        print(f"Failed to start CPU_Load_Graph_Parser.py: {e}")

if __name__ == '__main__':
    
    # Retrieve Jenkins workspace environment variable
    jenkins_workspace = os.environ.get('WORKSPACE')

    if jenkins_workspace:
        base_path = os.path.join(jenkins_workspace, "BVTRBS", "03_VariantDependent", "Customer")
    
        # Find the folder dynamically using glob
        matching_folders = glob.glob(os.path.join(base_path, "*"))
    
        if matching_folders:
            dynamic_path = matching_folders[0]  # Pick the first matching folder
        else:
            print("Warning: No matching folder found. Falling back to base path.")
            dynamic_path = base_path  # Fallback to base path if no folder is found
    else:
        print("Warning: WORKSPACE environment variable not set. Falling back to the current working directory.")
        dynamic_path = os.getcwd()  # Use the current working directory as the fallback path

    # Add dynamic_path to default source paths
    DEFAULT_SOURCE_PATHS.append(dynamic_path)

    print(f"Using dynamic path: {dynamic_path}")  # Debugging print

    #Check for cpu load results if found
    getCPULoadResults()
    
    parser = argparse.ArgumentParser(description="Generate an HTML report with extracted test data, failures, logs, and images.")
    parser.add_argument('html_file', type=str, nargs='?', default="Report_Sanity.html", help="Path to the HTML file. If not provided, the script will find one automatically.")
    parser.add_argument('keyword', type=str, nargs='?', default="Evaluate response", help="Keyword to search for in the file.")
    parser.add_argument('--source_paths', type=str, nargs='+', default=DEFAULT_SOURCE_PATHS, help="List of source directories.")
    parser.add_argument('--destination_path', type=str, default=DEFAULT_DESTINATION_PATH, help="Destination path for copied files.")
    args = parser.parse_args()

    #Automatically search for all report files in source paths
    found_html_files = find_html_files(DEFAULT_SOURCE_PATHS)
    if not found_html_files:
        exit(1)

    #Generate a consolidated Software Test Report of all HTML files found
    generate_html_report(found_html_files, args.source_paths, args.destination_path, args.keyword)

    #Clean up work spaces of old report files for next iterations on jenkins node
    print(f"Cleaning workspaces...")
    os.system("del /f /q /s C:\\JS\\ws\\develop\\sw\\Release\\FlashLog.txt")
    os.system("del /f /q /s C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\*.txt")
    os.system("del /f /q /s C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\*.xlsx")
    os.system("del /f /q /s C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\*jpg")
   
