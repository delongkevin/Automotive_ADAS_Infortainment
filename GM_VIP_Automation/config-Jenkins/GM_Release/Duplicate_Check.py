from pathlib import Path
import  logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

this_folder = Path(__file__).parent
deliverable_folder = this_folder / 'GM_Release_Prep/HWIODeliverable'
search_paths = {'HWIOAPPL', 'HWIOBOOT', 'HWIORPGM'}

duplicate_count = 0
deleted_count = 0

for target in search_paths:
    all_c_files = list((deliverable_folder / target).rglob('*.c'))
    all_h_files = list((deliverable_folder / target).rglob('*.h'))
    all_files = all_c_files + all_h_files
    file_list = dict()
    for some_file in all_files:
        relative_to_script_path = some_file.relative_to(deliverable_folder)
        if not some_file.is_file():
            logger.error(f"A non-file is named like a file: {some_file}")
            continue
        if some_file.name not in file_list:
            file_list[some_file.name] = set()
        file_list[some_file.name].add(relative_to_script_path)
    for filename in file_list:
        if len(file_list[filename]) <= 1:
            continue
        # compare the duplicates to see if they're all the same
        file_contents = dict()
        for some_file in file_list[filename]:
            with open(deliverable_folder / some_file, 'rb') as f:
                file_contents[some_file] = f.read()
        all_contents = set(file_contents.values())
        is_identical = len(all_contents) == 1

        files = '  - ' + '\n  - '.join(str(f) for f in file_list[filename])
        if is_identical:
            if len({str(f).replace('Test', 'Source') for f in file_list[filename]}) == 1:
                logger.debug(f'Header file was brought to both Source and Test folders, skipping: \n')
                continue
            logger.warning(f"{target} - Duplicate filename '{filename}' for identical files found in: \n{files}")
        else:
            logger.error(f"{target} - Conflicting duplicate filename '{filename}' for different files found in: \n{files}")
        duplicate_count += 1
logger.info(f"Found {duplicate_count} duplicate files and deleted {deleted_count} files.")






