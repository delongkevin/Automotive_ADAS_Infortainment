import re
import openpyxl
import sys
import os
import shlex
import base64
import matplotlib.pyplot as plt
from datetime import datetime

def clean_text(text):
    return "".join(c for c in text if c.isprintable())

def format_filename(search_string, file_path):
    base_name = os.path.splitext(os.path.basename(file_path))[0]  # Extract filename without extension
    formatted_string = search_string.replace(" ", "_").replace(":", "_").replace("/", "_")
    return f"{base_name}_{formatted_string}"  # Combine filename and search string to avoid conflicts

def normalize_spaces(text):
    return " ".join(text.split())  # Convert multiple spaces to a single space

def extract_first_numeric(line, search_string):
    search_string = normalize_spaces(search_string)  # Normalize search string before matching
    if search_string in normalize_spaces(line):  # Normalize log line too
        modified_line = line.replace(search_string, "").strip()
        numbers = re.findall(r"\d+\.\d+|\d+", modified_line)
        return float(numbers[0]) if numbers else None
    return None

def create_output_folder():
    timestamp = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")  # Add microseconds for uniqueness
    output_folder = os.path.join(f"C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\")
    os.makedirs(output_folder, exist_ok=True)
    return output_folder

def save_to_excel(extracted_data, search_string, file_path, include_cpu_load, output_folder):
    safe_search_string = format_filename(search_string, file_path)
    filename = os.path.join(output_folder, f"C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\output_{safe_search_string}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Data"
    
    ws.append(["Iteration", "Idle Value (%)"] + (["CPU Load (%)"] if include_cpu_load else []))

    for record in extracted_data:
        ws.append(record)
    
    wb.save(filename)
    print(f"Data for {search_string} saved to {filename}")
    return filename

def generate_graph(x_values, idle_values, cpu_load_values, search_string, file_path, include_cpu_load, title, xlabel, ylabel, show_labels, output_folder):
    if not idle_values:
        print(f"No numeric data to plot for {search_string}.")
        return

    safe_search_string = format_filename(search_string, file_path)
    graph_filename = os.path.join(output_folder, f"C:\\JS\\CT_Server_Standard_files_Continous_Testing\\python\\graph_{safe_search_string}.jpg")

    plt.figure(figsize=(10, 5))
    plt.plot(x_values, idle_values, marker='o', linestyle='-', color='b', label=f"{search_string} %")

    if include_cpu_load:
        plt.plot(x_values, cpu_load_values, marker='s', linestyle='--', color='r', label="CPU Load %")
    for i, val in enumerate(cpu_load_values):
        if val > 80:
            plt.plot(x_values[i], val, 'rx', markersize=10)

    # Calculate statistics for idle values
    min_idle = min(idle_values)
    max_idle = max(idle_values)
    avg_idle = sum(idle_values) / len(idle_values)

    # Calculate statistics for CPU load values
    if include_cpu_load:
        min_cpu = min(cpu_load_values)
        max_cpu = max(cpu_load_values)
        avg_cpu = sum(cpu_load_values) / len(cpu_load_values)

    # Determine Y range to dynamically position text
    min_y = min(idle_values + cpu_load_values) if include_cpu_load else min(idle_values)
    y_range = (max(idle_values + cpu_load_values) - min_y) if include_cpu_load else (max(idle_values) - min_y)
    bottom_y = min_y - (y_range * 0.15)  # Adjust text position dynamically

    # Adjust X positioning for the stats boxes
    left_x = x_values[0] - (max(x_values) * 0.05)  # Left-aligned near the start
    right_x = x_values[-1] + (max(x_values) * 0.05)  # Right-aligned near the end

    # Display Idle statistics at bottom-left
    stats_text_idle = f"Idle Min: {min_idle:.2f}%\nIdle Max: {max_idle:.2f}%\nIdle Avg: {avg_idle:.2f}%"
    plt.text(left_x, bottom_y, stats_text_idle, fontsize=10, 
             verticalalignment='top', horizontalalignment='left', 
             bbox=dict(boxstyle='round,pad=0.4', edgecolor='black', facecolor='white'))

    if include_cpu_load:
        # Display CPU statistics at bottom-right
        stats_text_cpu = f"CPU Min: {min_cpu:.2f}%\nCPU Max: {max_cpu:.2f}%\nCPU Avg: {avg_cpu:.2f}%"
        plt.text(right_x, bottom_y, stats_text_cpu, fontsize=10, 
                 verticalalignment='top', horizontalalignment='right', 
                 bbox=dict(boxstyle='round,pad=0.4', edgecolor='black', facecolor='white'))

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(f"{title} - {search_string}")
    plt.legend()
    plt.grid(True)

    # Adding data labels if enabled
    if show_labels:
        for i, idle_val in enumerate(idle_values):
            plt.text(x_values[i], idle_val, f"{idle_val:.2f}", fontsize=9, ha='right', va='bottom', color='blue')
        if include_cpu_load:
            for i, cpu_load_val in enumerate(cpu_load_values):
                plt.text(x_values[i], cpu_load_val, f"{cpu_load_val:.2f}", fontsize=9, ha='right', va='top', color='red')

    plt.savefig(graph_filename, format='jpg', bbox_inches='tight')
    print(f"Graph for {search_string} saved as {graph_filename}")
    plt.close()

def generate_html_report(output_folder, summary_results):
    html_filename = os.path.join(output_folder, "CPU_Load_SW_Test_Report.html")
    image_files = [f for f in os.listdir(output_folder) if f.endswith(".jpg")]

    with open(html_filename, "w") as f:
        f.write("""
        <html>
        <head>
        <title>CPU Load Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .summary-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            .summary-table th, .summary-table td { border: 1px solid #ccc; padding: 8px; text-align: center; }
            .fail { background-color: #f8d7da; color: #721c24; }
            .pass { background-color: #d4edda; color: #155724; }
            .grid-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 10px; }
            .grid-container img { width: 100%; border: 1px solid #ddd; border-radius: 5px; padding: 5px; background: #f9f9f9; }
        </style>
        </head>
        <body>
        <h2>CPU Load Summary Report</h2>
        <table class="summary-table">
        <tr><th>Search String</th><th>Status</th></tr>
        """)

        for search, status in summary_results:
            status_class = "fail" if status == "FAIL" else "pass"
            f.write(f"<tr class='{status_class}'><td>{search}</td><td>{status}</td></tr>")

        f.write("</table><div class='grid-container'>")

        for image in image_files:
            image_path = os.path.join(output_folder, image)
            with open(image_path, "rb") as img_file:
                base64_string = base64.b64encode(img_file.read()).decode("utf-8")
                f.write(f'<img src="data:image/jpeg;base64,{base64_string}" alt="{image}">\n')

        f.write("</div></body></html>")

    print(f"HTML report generated: {html_filename}")

def process_and_graph(file_path, search_strings, include_cpu_load, title, xlabel, ylabel, show_labels, output_folder):
    summary_results = []  # Store summary info for HTML
    global_failure = False

    for search_string in search_strings:
        extracted_data, x_values, idle_values, cpu_load_values = [], [], [], []
        with open(file_path, "r") as file:
            iteration = 1
            for line in file:
                first_numeric = extract_first_numeric(line, search_string)
                if first_numeric is not None:
                    cpu_load = 100 - first_numeric if include_cpu_load else None
                    extracted_data.append((iteration, first_numeric, cpu_load) if include_cpu_load else (iteration, first_numeric))
                    x_values.append(iteration)
                    idle_values.append(first_numeric)
                    if include_cpu_load:
                        cpu_load_values.append(cpu_load)
                    iteration += 1

        if extracted_data:
            save_to_excel(extracted_data, search_string, file_path, include_cpu_load, output_folder)
            generate_graph(x_values, idle_values, cpu_load_values, search_string, file_path, include_cpu_load, title, xlabel, ylabel, show_labels, output_folder)

            fail_detected = any(val > 80 for val in cpu_load_values) if include_cpu_load else False
            summary_results.append((search_string, "FAIL" if fail_detected else "PASS"))
            if fail_detected:
                global_failure = True
        else:
            summary_results.append((search_string, "NO DATA"))

    return summary_results, global_failure


    raise Exception("CPU Load Test Failed: One or more data points exceeded 80% CPU load.")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    command_list_path = os.path.join(script_dir, "Command_List.log")
    output_folder = create_output_folder()
    parsed_commands_file = os.path.join(output_folder, "Parsed_Commands.txt")
    all_summary_results = []
    any_failure = False

    if os.path.exists(command_list_path):
        with open(command_list_path, "r") as file:
            commands = [shlex.split(line.strip()) for line in file if line.strip()]

        with open(parsed_commands_file, "w") as log_file:
            log_file.write("Parsed Commands:\n")
            for cmd in commands:
                log_file.write(" ".join(cmd) + "\n")

        for cmd in commands:
            if len(cmd) < 7:
                print(f"Skipping invalid entry (expected 7 arguments, got {len(cmd)}): {' '.join(cmd)}")
                continue
            try:
                file_path = os.path.join(script_dir, cmd[0])
                search_string = normalize_spaces(cmd[1])
                include_cpu_load = cmd[2].lower() == "true"
                title, xlabel, ylabel = cmd[3:6]
                show_labels = cmd[6].lower() == "true"

                    # Retry logic if file does not exist
                if not os.path.exists(file_path):
                    print(f"[WARN] Log file not found: {file_path}")
                    print("[INFO] Attempting to launch log generation script...")

                    # Adjust this to your actual script or command
                    subprocess.run(["python", "CPU_Load_A72.py"], check=False)
                    time.sleep(15)  # Wait for logs to be generated

                # Check again after retry
                if not os.path.exists(file_path):
                    print(f"[ERROR] Still no log file after retry: {file_path}")
                    all_summary_results.append((search_string, "MISSING LOG"))
                    continue

                summary_results, had_failure = process_and_graph(
                    file_path,
                    [search_string],
                    include_cpu_load,
                    title,
                    xlabel,
                    ylabel,
                    show_labels,
                    output_folder
                )

                all_summary_results.extend(summary_results)
                if had_failure:
                    any_failure = True
            except Exception as e:
                print(f"Error processing command '{' '.join(cmd)}': {e}")

    generate_html_report(output_folder, all_summary_results)
    if any_failure:
        raise Exception("CPU Load Test Failed: One or more data points exceeded 80% CPU load.")
