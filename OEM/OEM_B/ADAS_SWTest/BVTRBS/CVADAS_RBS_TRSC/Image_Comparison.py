import cv2
import numpy as np
import os
import csv
import imageio.v2 as imageio
from datetime import datetime
import argparse
import time
import logging
import filelock
import tempfile
import psutil
import sys
import shutil
import json
from skimage.metrics import structural_similarity as ssim

# --- Configuration Helper Functions ---

def load_config(filepath='config.json'):
    """Loads configuration from a JSON file."""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.warning("Config file is corrupted. Using defaults.")
                return {}
    return {}

def save_config(config_data, filepath='config.json'):
    """Saves configuration to a JSON file."""
    with open(filepath, 'w') as f:
        json.dump(config_data, f, indent=4)
    logging.info(f"Configuration saved to {filepath}")


# --- Comparison and Image Generation Functions ---
def create_side_by_side_comparison(master_frame, captured_frame, diff_percent):
    """Creates a side-by-side image with labels for visual comparison."""
    #To ensure the images can be stacked, they need the same height.
    h1, w1 = master_frame.shape[:2]
    h2, w2 = captured_frame.shape[:2]

    target_height = 480

    #Scale width proportionally
    if h1 == 0 or h2 == 0: #Prevent division by zero if a frame is empty
        logging.error("One of the frames for side-by-side comparison is empty or invalid.")
     #   Return a placeholder or raise an error, here returning captured_frame to avoid crash
        return captured_frame

    master_scaled = cv2.resize(master_frame, (int(w1 * target_height / h1) if h1 else w1, target_height))
    captured_scaled = cv2.resize(captured_frame, (int(w2 * target_height / h2) if h2 else w2, target_height))


    #Add labels to each image
    cv2.putText(master_scaled, "Master Frame", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(captured_scaled, "Captured Frame (Difference)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    #Combine the two images horizontally
    comparison_image = cv2.hconcat([master_scaled, captured_scaled])

    #Add the difference percentage to the final image
    diff_text = f"Difference: {diff_percent:.2f}%"
    cv2.putText(comparison_image, diff_text, (10, comparison_image.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    return comparison_image

def compare_pixel_diff(frame1, frame2, **kwargs):
    """
    Compares two frames using absolute pixel difference and thresholding.
    Returns a percentage of difference.
    """
    if frame1 is None or frame2 is None: return 0
    try:
        diff = cv2.absdiff(frame1, frame2)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
        non_zero_count = np.count_nonzero(thresh)
        total_pixels = thresh.shape[0] * thresh.shape[1]
        if total_pixels == 0:
            return 0
        return (non_zero_count / total_pixels) * 100
    except cv2.error as e:
        logging.error(f"OpenCV error in compare_pixel_diff: {e}")
        return 0

def compare_ssim(frame1, frame2, **kwargs):
    """
    Compares two frames using the Structural Similarity Index (SSIM).
    Returns a "dissimilarity" percentage.
    """
    if frame1 is None or frame2 is None:
        return 0
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    (score, _) = ssim(gray1, gray2, full=True)
   # Return dissimilarity percentage
    return (1 - score) * 100

def compare_background_subtraction(frame, back_sub_model, **kwargs):
    """
    Uses a background subtraction model to find foreground objects.
    Returns the percentage of the frame that is foreground.
    """
    if frame is None or back_sub_model is None:
        return 0
    fg_mask = back_sub_model.apply(frame)
    non_zero_count = np.count_nonzero(fg_mask)
    total_pixels = fg_mask.shape[0] * fg_mask.shape[1]
    if total_pixels == 0:
        return 0
    return (non_zero_count / total_pixels) * 100

def run_comparison_method(method, frame1, frame2, back_sub_model=None):
    """Router to call the selected comparison function."""
    if method == 'pixel_diff':
        return compare_pixel_diff(frame1, frame2)
    elif method == 'ssim':
        return compare_ssim(frame1, frame2)
    elif method == 'background_subtraction':
        return compare_background_subtraction(frame1, back_sub_model)
    else:
        logging.error(f"Unknown comparison method: {method}")
        return 0

# --- Media and File Operations ---

def set_master_frame_headless(camera_index, output_dir, config):
    """Captures a single frame and saves it as the master frame for automation."""
    logging.info(f"Attempting to set master frame from camera index {camera_index}.")
    cap = None
    try:
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            logging.error(f"Could not open camera at index {camera_index}.")
            sys.exit(1)

        ret, frame = cap.read()
        if not ret or frame is None:
            logging.error("Failed to capture a frame from the camera.")
            sys.exit(1)

        # If an ROI is defined in the config, crop the frame before saving
        roi_str = config.get('roi_str')
        if roi_str:
            try:
                x, y, w, h = map(int, roi_str.split(','))
                frame = frame[y:y+h, x:x+w]
                logging.info(f"Applied ROI { (x,y,w,h) } to the new master frame.")
            except Exception as e:
                logging.error(f"Could not apply ROI from config: {e}. Using full frame.")

        os.makedirs(output_dir, exist_ok=True)
        master_frame_path = os.path.join(output_dir, "current_master_frame.jpg")

        cv2.imwrite(master_frame_path, frame)
        logging.info(f"Successfully set new master frame: {master_frame_path}")

    except Exception as e:
        logging.error(f"An error occurred while setting the master frame: {e}")
        sys.exit(1)
    finally:
        if cap and cap.isOpened():
            cap.release()

def compare_to_master_headless(camera_index, output_dir, threshold, method, config):
    """Captures a frame, saves it, compares it to the master frame, and exits with a pass/fail code."""
    master_frame_path = os.path.join(output_dir, "current_master_frame.jpg")

    if not os.path.exists(master_frame_path):
        logging.error(f"Master frame not found at '{master_frame_path}'. Cannot perform comparison.")
        logging.error("Please run with --capture_image --master_frame_mode first to set it.")
        sys.exit(2)

    master_frame = cv2.imread(master_frame_path)
    if master_frame is None:
        logging.error(f"Failed to load master frame from '{master_frame_path}'. It may be corrupted.")
        sys.exit(2)

    logging.info("Loaded master frame for comparison.")
    cap = None
    try:
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            logging.error(f"Could not open camera at index {camera_index}.")
            sys.exit(1)

        ret, captured_frame_full = cap.read()
        if not ret or captured_frame_full is None:
            logging.error("Failed to capture a new frame from the camera for comparison.")
            sys.exit(1)
        
        logging.info("Captured new frame for comparison.")
        captured_frame_for_comparison = captured_frame_full.copy()

        # If ROI is defined, apply it to the frame we will use for comparison.
        roi_str = config.get('roi_str')
        if roi_str:
            try:
                x, y, w, h = map(int, roi_str.split(','))
                captured_frame_for_comparison = captured_frame_for_comparison[y:y+h, x:x+w]
                logging.info(f"Applied ROI {(x,y,w,h)} to the captured frame for comparison.")
            except Exception as e:
                logging.error(f"Could not apply ROI from config: {e}. Using full frame.")
        
        # Ensure frames have the same size for comparison
        if master_frame.shape != captured_frame_for_comparison.shape:
            logging.warning(f"Master {master_frame.shape} and captured {captured_frame_for_comparison.shape} shapes differ. Resizing.")
            captured_frame_for_comparison = cv2.resize(captured_frame_for_comparison, (master_frame.shape[1], master_frame.shape[0]))

        # Perform the comparison
        diff_percent = run_comparison_method(method, captured_frame_for_comparison, master_frame)
        logging.info(f"Comparison Result: Difference = {diff_percent:.2f}%, Threshold = {threshold:.2f}%")
        
        # Determine pass/fail status
        if diff_percent > threshold:
            status = "FAIL"
            logging.error(f"FAIL: Difference ({diff_percent:.2f}%) exceeds threshold ({threshold:.2f}%).")
        else:
            status = "PASS"
            logging.info(f"PASS: Difference ({diff_percent:.2f}%) is within threshold ({threshold:.2f}%).")

        # Create directory for captures
        comparison_captures_dir = os.path.join(output_dir, "comparison_captures")
        os.makedirs(comparison_captures_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Generate and save the side-by-side comparison image
        comparison_image = create_side_by_side_comparison(master_frame, captured_frame_for_comparison, diff_percent)
        sbs_save_filename = f"{status}_side_by_side_{timestamp}_diff_{diff_percent:.2f}.jpg"
        sbs_save_path = os.path.join(comparison_captures_dir, sbs_save_filename)
        cv2.imwrite(sbs_save_path, comparison_image)
        logging.info(f"Saved side-by-side comparison image to: {sbs_save_path}")

        # Save the raw captured frame
        raw_save_filename = f"{status}_capture_{timestamp}_diff_{diff_percent:.2f}.jpg"
        raw_save_path = os.path.join(comparison_captures_dir, raw_save_filename)
        cv2.imwrite(raw_save_path, captured_frame_full)
        logging.info(f"Saved raw comparison capture to: {raw_save_path}")

        # Exit with the correct code
        if status == "FAIL":
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        logging.error(f"An error occurred during headless comparison: {e}")
        sys.exit(1)
    finally:
        if cap and cap.isOpened():
            cap.release()

def export_media(detected_frames_paths, output_dir, export_format="gif", gif_duration_ms=200, video_fps=5):
    """Exports detected frames as a GIF or video."""
    if not detected_frames_paths:
        logging.warning("No frames detected to export.")
        return

    if export_format == "gif":
        gif_path = os.path.join(output_dir, "detected_changes.gif")
        images = []
        for img_path in detected_frames_paths:
            try: images.append(imageio.imread(img_path))
            except FileNotFoundError: logging.warning(f"Image file not found for GIF: {img_path}. Skipping.")
            except Exception as e: logging.warning(f"Could not read image {img_path} for GIF: {e}. Skipping.")
        if images:
            try:
                imageio.mimsave(gif_path, images, duration=gif_duration_ms / 1000.0)
                logging.info(f"GIF saved: {gif_path}")
            except Exception as e: logging.error(f"Failed to save GIF: {e}")
        else: logging.warning("No valid images to create GIF.")
    elif export_format == "video":
        video_path = os.path.join(output_dir, "detected_changes.avi")
        try:
            if not detected_frames_paths:
                return
            first_frame_img = cv2.imread(detected_frames_paths[0])
            if first_frame_img is None:
                logging.error(f"Could not read first frame for video export: {detected_frames_paths[0]}")
                return
            height, width, _ = first_frame_img.shape
            video_writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*'XVID'), video_fps, (width, height))
            for img_path in detected_frames_paths:
                frame = cv2.imread(img_path)
                if frame is not None: video_writer.write(frame)
                else: logging.warning(f"Could not read frame {img_path} for video. Skipping.")
            video_writer.release()
            logging.info(f"Video saved: {video_path}")
        except Exception as e:
            logging.error(f"Failed to write video: {e}")
    else:
        logging.warning(f"Unknown export format: {export_format}. Choose 'gif' or 'video'.")

def _save_quality_issue_frame(original_path, quality_base_dir, issue_name):
    """Helper function to save a frame to a specific quality issue subfolder."""
    issue_dir = os.path.join(quality_base_dir, issue_name)
    try:
        os.makedirs(issue_dir, exist_ok=True)
        shutil.copy2(original_path, os.path.join(issue_dir, os.path.basename(original_path)))
        logging.info(f"Frame classified as {issue_name} and copied: {os.path.basename(original_path)}")
    except Exception as e:
        logging.error(f"Could not copy frame to {issue_name} folder: {e}")

# --- Core Logic and Checks ---

def find_available_camera(max_indices_to_check=5):
    """Finds the first available camera index."""
    for i in range(max_indices_to_check):
        cap_test = cv2.VideoCapture(i)
        if cap_test.isOpened():
            logging.info(f"Found available camera at index: {i}")
            cap_test.release()
            return i
        cap_test.release()
    return None

def handle_script_failure(message, instance_lock_obj, pid_file_path_to_clean, cap_obj, writer_obj):
    """Centralized failure handler for graceful shutdown."""
    logging.error(f"SCRIPT FAILURE: {message}")
    if cap_obj and cap_obj.isOpened(): cap_obj.release()
    if writer_obj: writer_obj.release()
    if instance_lock_obj and instance_lock_obj.is_locked:
        instance_lock_obj.release()
        try:
            if os.path.exists(pid_file_path_to_clean): os.remove(pid_file_path_to_clean)
        except OSError as e:
            logging.warning(f"Could not remove PID file {pid_file_path_to_clean}: {e}")
    logging.info(f"--- Application instance PID {os.getpid()} exiting with FAILURE STATUS ---")
    sys.exit(1)

def check_frame_distortion(frame, black_thresh, edge_margin_factor, solid_area_thresh, std_dev_thresh, output_dir_for_tuning=None, save_tuning_frames=True, current_filename_base="distorted"):
    """Checks for basic frame distortion like large solid/black bars at edges."""
    if frame is None:
        return True
    h, w = frame.shape[:2]
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    margin_h, margin_w = int(h * edge_margin_factor), int(w * edge_margin_factor)
    regions_to_check = {
        "top": gray_frame[0:margin_h, :], "bottom": gray_frame[h - margin_h:h, :],
        "left": gray_frame[:, 0:margin_w], "right": gray_frame[:, w - margin_w:w]
    }
    for name, region in regions_to_check.items():
        if region.size == 0: continue
        dark_pixels = np.sum(region < black_thresh)
        if (dark_pixels / region.size) >= solid_area_thresh and np.std(region) < std_dev_thresh:
            logging.warning(f"Distortion suspected: Solid/dark bar detected in '{name}' region.")
            if save_tuning_frames and output_dir_for_tuning:
                try:
                    os.makedirs(output_dir_for_tuning, exist_ok=True)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                    save_path = os.path.join(output_dir_for_tuning, f"{current_filename_base}_{timestamp}.jpg")
                    cv2.imwrite(save_path, frame)
                    logging.info(f"Saved suspected distorted frame for tuning: {save_path}")
                except Exception as e:
                    logging.error(f"Could not save frame for distortion tuning: {e}")
            return True
    return False

def check_lighting_and_color(frame, dark_thresh, bright_thresh, black_screen_std_dev, output_dir_quality, original_frame_path, save_issues=False):
    """Checks for overall brightness issues and saves problematic frames."""
    if frame is None: return ["frame_none"]
    issues = []
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray_frame)

    if mean_brightness < (dark_thresh / 2) and np.std(gray_frame) < black_screen_std_dev:
        issues.append("black_screen")
        if save_issues: _save_quality_issue_frame(original_frame_path, output_dir_quality, "black_screen")
    elif mean_brightness < dark_thresh:
        issues.append("too_dark")
        if save_issues: _save_quality_issue_frame(original_path, output_dir_quality, "too_dark")
    elif mean_brightness > bright_thresh:
        issues.append("too_bright")
        if save_issues: _save_quality_issue_frame(original_frame_path, output_dir_quality, "too_bright")
    return issues

def draw_change_rectangles(original_frame, prev_frame_for_diff, min_contour_area, output_dir_changes_boxed, original_frame_path_to_copy, save_boxed_frames=False):
    """Draws green rectangles around areas of significant change."""
    if original_frame is None or prev_frame_for_diff is None: return original_frame
    frame_with_boxes = original_frame.copy()
    try:
        diff = cv2.absdiff(prev_frame_for_diff, original_frame)
        gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, thresh_diff = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
        dilated_thresh = cv2.dilate(thresh_diff, np.ones((5, 5), np.uint8), iterations=2)
        contours, _ = cv2.findContours(dilated_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        num_boxes_drawn = 0
        for contour in contours:
            if cv2.contourArea(contour) > min_contour_area:
                x, y, w, h = cv2.boundingRect(contour)
                cv2.rectangle(frame_with_boxes, (x, y), (x + w, y + h), (0, 255, 0), 2)
                num_boxes_drawn += 1
        if save_boxed_frames and num_boxes_drawn > 0:
            os.makedirs(output_dir_changes_boxed, exist_ok=True)
            viz_save_path = os.path.join(output_dir_changes_boxed, os.path.basename(original_frame_path_to_copy).replace(".jpg", "_viz.jpg"))
            cv2.imwrite(viz_save_path, frame_with_boxes)
            logging.info(f"Saved frame with change boxes: {viz_save_path}")
    except Exception as e:
        logging.error(f"Could not save/process frame with change boxes: {e}")
    return frame_with_boxes

def draw_ui_text(frame, text, position=(20, 40), color=(0, 255, 255)):
    """Draws text with a background on the frame for better visibility."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
    text_w, text_h = text_size
    #Add a black rectangle background
    cv2.rectangle(frame, (position[0] - 5, position[1] + 5), (position[0] + text_w + 5, position[1] - text_h - 5), (0,0,0), -1)
    cv2.putText(frame, text, position, font, font_scale, color, thickness)

# --- Main Application Logic ---
def main():
    #Load saved configuration first to use for argument defaults
    saved_config = load_config()

    parser = argparse.ArgumentParser(description="Advanced Camera Tester with Master Frame Comparison.")

    #Mode, ROI and Camera Arguments using saved config for defaults
    parser.add_argument("--capture_image", action="store_true", help="Enable automated capture mode. Use with --master_frame_mode to set the master frame, or alone to compare against it.")
    parser.add_argument("--exit-on-first-diff", action="store_true", help="Gracefully exit the script after the first difference is detected and saved.")
    parser.add_argument("--master_frame_mode", action="store_true", help="Enable master frame comparison mode. In automation, use with --capture_image to set the master frame.")
    parser.add_argument("--roi", type=str, default=saved_config.get('roi_str'),
                        help="Manually specify ROI as 'x,y,w,h'. Skips interactive selection.")
    parser.add_argument("--camera_index", type=int, default=saved_config.get('camera_index'),
                        help="Specify camera index. Auto-detects if not set.")
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless mode (no GUI windows). Requires --roi to be specified if not in config.")

    #General Args
    parser.add_argument("--output_dir", type=str, default=os.path.join(os.getcwd(), "camera_test_output"), help="Directory for all outputs.")
    parser.add_argument("--duration", type=int, default=1000, help="Maximum recording duration in seconds.")
    parser.add_argument("--log_level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Logging level.")
    parser.add_argument("--no_console_log", action="store_true", help="Disable console logging.")

    #Capture & Export Args
    parser.add_argument("--fps_capture", type=int, default=30, help="Desired FPS for camera capture.")
    parser.add_argument("--video_codec", type=str, default="XVID", help="Codec for raw video output (e.g., XVID, mp4v).")
    parser.add_argument("--export_format", type=str, default="gif", choices=["gif", "video", "none"], help="Export format for detected changes.")
    parser.add_argument("--gif_frame_duration", type=int, default=200, help="Duration (ms) per frame in exported GIF.")
    parser.add_argument("--video_export_fps", type=int, default=5, help="FPS for exported video of changes.")

    #Comparison & Detection Args
    parser.add_argument("--compare_method", type=str, default="pixel_diff", choices=["pixel_diff", "ssim", "background_subtraction"], help="Method for frame comparison.")
    parser.add_argument("--threshold", type=float, default=10.0, help="Difference percentage (0-100) to trigger change detection.")
    parser.add_argument("--draw_change_boxes", action="store_true", default=True, help="Draw boxes on changed frames and save visualizations.")
    parser.add_argument("--min_change_area", type=int, default=100, help="Minimum contour area to be considered a change.")

    #Performance & Failure Args
    parser.add_argument("--min_fps_factor", type=float, default=0.70, help="Script fails if measured FPS drops below (desired_fps * this factor).")
    parser.add_argument("--fps_eval_interval", type=int, default=10, help="Interval (seconds) to evaluate FPS.")

    #Quality Check Args
    parser.add_argument('--enable-distortion-check', dest='distortion_check', action='store_true', help="Enable checks for edge/bar distortion (default).")
    parser.add_argument('--no-distortion-check', dest='distortion_check', action='store_false', help="Disable checks for edge/bar distortion.")
    parser.set_defaults(distortion_check=True)
    parser.add_argument("--distortion_black_threshold", type=int, default=30, help="Pixel intensity below this is 'black' for distortion.")
    parser.add_argument("--distortion_edge_margin", type=float, default=0.15, help="Percentage of frame to check as edge margin.")
    parser.add_argument("--distortion_solid_area_threshold", type=float, default=0.85, help="Percentage of margin that must be 'black' to flag distortion.")
    parser.add_argument("--distortion_std_dev_thresh", type=int, default=10, help="Max standard deviation for a 'solid' bar.")
    parser.add_argument("--save_tuning_frames", action="store_true", help="Save frames flagged by distortion check for tuning.")

    parser.add_argument("--enable_lighting_check", action="store_true", default=True, help="Enable checks for lighting issues.")
    parser.add_argument("--brightness_dark_thresh", type=int, default=60, help="Mean brightness below this is 'too_dark'.")
    parser.add_argument("--brightness_bright_thresh", type=int, default=200, help="Mean brightness above this is 'too_bright'.")
    parser.add_argument("--black_screen_std_dev_thresh", type=int, default=5, help="Max standard deviation for a 'black_screen' frame.")

    args = parser.parse_args()

   # --- Setup Output Directories ---
    os.makedirs(args.output_dir, exist_ok=True)
    detected_frames_output_dir = os.path.join(args.output_dir, "detected_frames_capture")
    quality_issues_base_dir = os.path.join(args.output_dir, "quality_issues")
    tuning_distortion_output_dir = os.path.join(quality_issues_base_dir, "for_tuning_distortion")
    changes_boxed_output_dir = os.path.join(quality_issues_base_dir, "significant_change_with_boxes")

    #--- Setup Logging ---
    log_file_path = os.path.join(args.output_dir, "camera_tester_activity.log")
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, args.log_level.upper()))
    if logger.hasHandlers(): logger.handlers.clear()
    file_handler = logging.FileHandler(log_file_path, mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - PID:%(process)d - %(message)s'))
    logger.addHandler(file_handler)
    if not args.no_console_log:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(console_handler)

    logging.info(f"--- Application instance started with PID {os.getpid()} ---")
    logging.debug(f"Full command line arguments: {sys.argv}")

    #--- Auto-detect camera index if not specified ---
    camera_idx_to_use = args.camera_index
    if camera_idx_to_use is None:
        camera_idx_to_use = find_available_camera()
        if camera_idx_to_use is None:
            logging.error("Could not find an available camera.")
            sys.exit(1)
        saved_config['camera_index'] = camera_idx_to_use
        save_config(saved_config)

    # --- Handle Automated Capture/Comparison Modes ---
    if args.capture_image:
        if args.master_frame_mode:
            logging.info("AUTOMATION: Setting new master frame.")
            set_master_frame_headless(camera_idx_to_use, args.output_dir, saved_config)
            sys.exit(0)
        else:
            logging.info("AUTOMATION: Comparing new capture to master frame.")
            compare_to_master_headless(
                camera_idx_to_use,
                args.output_dir,
                args.threshold,
                args.compare_method,
                saved_config
            )
            # The script will exit with a pass/fail code inside the function
            # This is a fallback exit.
            sys.exit(0)

    #--- Setup Singleton Lock ---
    lock_dir = os.path.join(tempfile.gettempdir(), "camera_tester_locks")
    os.makedirs(lock_dir, exist_ok=True)
    lock_file_path = os.path.join(lock_dir, f"camera_instance_cam{camera_idx_to_use}.lock")
    pid_file_path = os.path.join(lock_dir, f"camera_instance_cam{camera_idx_to_use}.pid")
    instance_lock = filelock.FileLock(lock_file_path, timeout=0.1)

    cap, raw_video_writer = None, None

    try:
        instance_lock.acquire()
        with open(pid_file_path, "w") as f: f.write(str(os.getpid()))
        logging.info(f"Lock acquired by PID {os.getpid()} for camera index {camera_idx_to_use}.")

        os.makedirs(detected_frames_output_dir, exist_ok=True)
        csv_file_path = os.path.join(args.output_dir, "detection_log.csv")
        with open(csv_file_path, mode='w', newline='') as f:
            csv.writer(f).writerow(["Timestamp", "Session Elapsed (s)", "Difference (%)", "Method", "Saved Frame", "Quality Issues"])

     #   --- Camera and Video Writer Initialization ---
        cap = cv2.VideoCapture(camera_idx_to_use)
        if not cap.isOpened(): raise RuntimeError(f"Could not open camera index {camera_idx_to_use}.")

        cap.set(cv2.CAP_PROP_FPS, args.fps_capture)
        desired_fps = cap.get(cv2.CAP_PROP_FPS) or float(args.fps_capture)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width == 0 or height == 0: raise RuntimeError("Camera returned invalid frame dimensions.")

        logging.info(f"Camera opened: {width}x{height} @ {desired_fps:.2f} FPS (target).")

        raw_video_path = os.path.join(args.output_dir, "full_recorded_video.avi")
        raw_video_writer = cv2.VideoWriter(raw_video_path, cv2.VideoWriter_fourcc(*args.video_codec), desired_fps, (width, height))

      #  --- ROI SELECTION LOGIC ---
        roi_coords = None
        if args.roi:
            try:
                roi_coords = tuple(map(int, args.roi.split(',')))
                logging.info(f"Using ROI from command-line/config: {roi_coords}")
            except Exception as e:
                logging.error(f"Invalid --roi format. Use 'x,y,w,h'. Error: {e}")
                sys.exit(1)
        elif not args.headless:
            ret, first_frame = cap.read()
            if not ret:
                raise RuntimeError("Could not read frame from camera to select ROI.")

            # --- Resize frame for a manageable ROI selection window ---
            h, w = first_frame.shape[:2]
            max_dim_for_selection = 960
            scale = 1.0
            
            if h > max_dim_for_selection or w > max_dim_for_selection:
                scale = max_dim_for_selection / max(h, w)
                selection_frame = cv2.resize(first_frame, (int(w * scale), int(h * scale)))
            else:
                selection_frame = first_frame

            logging.info("Please select the Region of Interest (ROI) in the window and press ENTER or SPACE.")
            
            # Use the resized frame for selection
            roi_coords_resized = cv2.selectROI("Select Area of Interest and Press ENTER", selection_frame, fromCenter=False, showCrosshair=True)
            cv2.destroyWindow("Select Area of Interest and Press ENTER")
            
            # --- Scale coordinates back to the original frame size ---
            if roi_coords_resized and roi_coords_resized[2] > 0 and roi_coords_resized[3] > 0:
                x_r, y_r, w_r, h_r = roi_coords_resized
                roi_coords = (int(x_r / scale), int(y_r / scale), int(w_r / scale), int(h_r / scale))
            else:
                roi_coords = (0,0,0,0) # Invalid ROI

            if not roi_coords or roi_coords[2] == 0 or roi_coords[3] == 0:
                logging.error("No valid ROI selected. Exiting.")
                sys.exit(1)

            saved_config['roi_str'] = ",".join(map(str, roi_coords))
            save_config(saved_config)
            logging.info(f"New ROI selected and saved: {roi_coords}")
        else: #Headless mode AND no ROI provided via --roi or config.json
            logging.error("Cannot run in headless mode without a defined ROI. Please specify --roi or have it in config.json.")
            sys.exit(1)

        #--- Main Loop Setup ---
        master_frame = None
        prev_cropped_frame = None

        if not args.headless:
            window_name = "Camera Feed - Press 'm' to set Master, 'q' to quit"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

        logging.info(f"Starting monitoring (PID: {os.getpid()}).")
        if not args.headless:
             logging.info("Press 'm' to set master frame, 'q' to quit in the video window.")
        if args.headless and args.master_frame_mode:
            logging.warning("Running in --master_frame_mode and --headless. Master frame cannot be set interactively.")
            logging.warning("Ensure master frame is set by other means or consider frame-to-frame comparison for headless runs if master is not pre-loaded.")


        back_sub_model = None
        if args.compare_method == 'background_subtraction':
            back_sub_model = cv2.createBackgroundSubtractorKNN()
            logging.info("Using Background Subtraction method. Allowing model to warm up.")

        session_start_time = time.time()
        fps_eval_start_time = time.time()
        fps_eval_frame_count, distortion_strikes = 0, 0
        detected_frames_paths = []

        #--- Main Execution Loop ---
        while True:
            elapsed = time.time() - session_start_time
            if args.duration and elapsed > args.duration:
                logging.info(f"Duration of {args.duration}s reached.")
                break

            ret, frame = cap.read()
            if not ret:
                logging.warning("Could not read frame from camera stream.")
                if not cap.isOpened(): break
                time.sleep(0.5)
                ret, frame = cap.read()
                if not ret:
                    raise RuntimeError("Failed to read frame persistently.")

            raw_video_writer.write(frame)

         #   --- APPLY ROI CROP TO EVERY FRAME ---
            x, y, w, h = roi_coords
            cropped_frame = frame[y:y+h, x:x+w]

            key = -1
            display_frame = None
            if not args.headless:
                display_frame = frame.copy()
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    logging.info("'q' pressed. Shutting down.")
                    break

            fps_eval_frame_count += 1

          #  --- Run Checks and Comparison on the CROPPED frame ---
            if args.distortion_check:
                if check_frame_distortion(cropped_frame, args.distortion_black_threshold, args.distortion_edge_margin, args.distortion_solid_area_threshold, args.distortion_std_dev_thresh, tuning_distortion_output_dir, args.save_tuning_frames):
                    distortion_strikes += 1
                    time.sleep(60) #add delay for video to stabilize
                    if distortion_strikes >= 10:
                        raise RuntimeError("Max distortion strikes reached.")
                else:
                    distortion_strikes = 0

           # --- Main Comparison Logic ---
            diff_percent = 0.0
            if args.master_frame_mode:
                if not args.headless and key == ord('m'):
                    master_frame = cropped_frame.copy()
                    master_frame_path = os.path.join(args.output_dir, "current_master_frame.jpg")
                    cv2.imwrite(master_frame_path, master_frame)
                    logging.info("="*50)
                    logging.info(f"--- MASTER FRAME SET. All subsequent frames will be compared to this baseline. ---")
                    logging.info(f"--- Reference image saved: {master_frame_path} ---")
                    logging.info("="*50)

                if master_frame is not None:
                    if not args.headless: draw_ui_text(display_frame, "STATUS: Master Frame is SET. Press 'm' to update.")
                    diff_percent = run_comparison_method(args.compare_method, cropped_frame, master_frame)
                elif not args.headless:
                    draw_ui_text(display_frame, "STATUS: Waiting for Master Frame. Press 'm' to set.")
            else: #Frame-to-frame mode
                if not args.headless and key == ord('m'):
                    logging.warning("Key 'm' pressed, but script is not in master frame mode.")
                    logging.warning("To enable this feature, please run the script with the '--master_frame_mode' flag.")

                if prev_cropped_frame is not None:
                    diff_percent = run_comparison_method(args.compare_method, cropped_frame, prev_cropped_frame)
                prev_cropped_frame = cropped_frame.copy()

            #--- Difference Detection and Artifact Generation ---
            if diff_percent > args.threshold:
                timestamp = datetime.now()
                ts_str = timestamp.strftime('%Y%m%d_%H%M%S_%f')[:-3]
                filename = f"change_{ts_str}.jpg"
                save_path = os.path.join(detected_frames_output_dir, filename)

                cv2.imwrite(save_path, frame) #Save the original, full-size frame for context
                detected_frames_paths.append(save_path)
                log_msg_source = "vs MASTER" if args.master_frame_mode and master_frame is not None else "vs PREVIOUS"
                logging.info(f"CHANGE DETECTED ({diff_percent:.2f}% {log_msg_source}): Saved FULL frame {filename}")

             #   Create and save the side-by-side comparison image
                comparison_ref_frame = master_frame if args.master_frame_mode and master_frame is not None else prev_cropped_frame
                if comparison_ref_frame is not None:
                    comparison_image = create_side_by_side_comparison(comparison_ref_frame, cropped_frame, diff_percent)
                    comparison_filename = f"change_{ts_str}_comparison.jpg"
                    comparison_save_path = os.path.join(detected_frames_output_dir, comparison_filename)
                    cv2.imwrite(comparison_save_path, comparison_image)
                    logging.info(f"Saved side-by-side comparison image: {comparison_filename}")

              #  Run Quality Checks
                quality_issues = []
                if args.enable_lighting_check:
                    os.makedirs(quality_issues_base_dir, exist_ok=True)
                    quality_issues = check_lighting_and_color(cropped_frame, args.brightness_dark_thresh, args.brightness_bright_thresh, args.black_screen_std_dev_thresh, quality_issues_base_dir, save_path, True)

                if args.draw_change_boxes:
                    draw_change_rectangles(cropped_frame, comparison_ref_frame, args.min_change_area, changes_boxed_output_dir, save_path, True)

                #Log to CSV
                with open(csv_file_path, 'a', newline='') as f:
                    csv.writer(f).writerow([ts_str, f"{elapsed:.2f}", f"{diff_percent:.2f}", args.compare_method, save_path, ", ".join(quality_issues) or "None"])

               # Check if the script should exit on this difference
                if args.exit_on_first_diff:
                    logging.info("--exit-on-first-diff flag is set. Shutting down after first detected change.")
                    break #Exit the while loop gracefully

            if not args.headless:
                # Define a fixed size for the display window and resize the frame
                fixed_display_size = (960, 540) # Width, Height
                display_frame = cv2.resize(display_frame, fixed_display_size, interpolation=cv2.INTER_AREA)
                cv2.imshow(window_name, display_frame)

            #--- FPS Evaluation ---
            eval_interval = time.time() - fps_eval_start_time
            if eval_interval >= args.fps_eval_interval:
                actual_fps = fps_eval_frame_count / eval_interval
                logging.info(f"FPS Check: Measured ~{actual_fps:.2f} FPS over last {eval_interval:.1f}s.")
                if actual_fps < (desired_fps * args.min_fps_factor):
                    raise RuntimeError(f"Measured FPS ({actual_fps:.2f}) is below threshold.")
                fps_eval_frame_count = 0
                fps_eval_start_time = time.time()

    except (KeyboardInterrupt, SystemExit) as e:
        logging.info(f"Script stopped by user or system exit: {type(e).__name__}")
    except filelock.Timeout:
        logging.warning(f"Another instance is already running for camera {camera_idx_to_use}. This instance will exit.")
    except Exception as e:
        handle_script_failure(f"A critical error occurred: {e}", instance_lock, pid_file_path, cap, raw_video_writer)
    finally:
        #--- Graceful Cleanup ---
        if not args.headless: #Only destroy windows if they were created
            cv2.destroyAllWindows()
        if cap and cap.isOpened(): cap.release()
        if raw_video_writer: raw_video_writer.release()
        logging.info("Camera and video writer released.")

        if args.export_format != "none" and detected_frames_paths:
            logging.info(f"Exporting {len(detected_frames_paths)} frames as {args.export_format}...")
            export_media(detected_frames_paths, args.output_dir, args.export_format, args.gif_frame_duration, args.video_export_fps)

        if instance_lock.is_locked:
            instance_lock.release()
            try:
                if os.path.exists(pid_file_path): os.remove(pid_file_path)
            except OSError: pass
            logging.info(f"Lock released by PID {os.getpid()}.")

        logging.info(f"--- Application instance PID {os.getpid()} ended ---")

if __name__ == "__main__":
    main()