from pathlib import Path

import os
import sys
import json


def _parse_cct(cct_name):
    with open(cct_name) as cct_file:
        header_string = ''
        for line in cct_file:
            line = line.strip()
            if line and line[0] == '*':
                header_string += line[1:]
            else:
                break
    return json.loads(header_string)


def _read_syshdr(stub_dir):
    syshdr_path = os.path.join(stub_dir, 'syshdr.lst')
    if not os.path.exists(syshdr_path):
        return []
    with open(syshdr_path, 'r') as syshdr_file:
        return syshdr_file.read().splitlines()


def _find_stub_header(paths, directory):
    for path in paths:
        if os.path.basename(path) == directory:
            return path
    return None


# Don't add all stub folder directories. Only if it's top level or there are .h files in there.
# Returns short name of folder or None if we should not add it.
def _add_directory(directory, file_names, directory_names, stub_dir, added_directories):
    short_name = directory[len(stub_dir):]
    sep_count = short_name.count(os.sep)
    add_directory = False
    if sep_count == 1 and len(file_names) != 0:
        add_directory = True
    elif sep_count > 1 and len(directory_names) != 0:
        add_directory = True
        for added_directory in added_directories:
            if short_name.startswith(added_directory):
                add_directory = False
    return short_name if add_directory else None


# Add include paths for CCT stub directories and syshdr.lst files (if present).
def add_stub_and_syshdr_includes():
    try:
        # template settings to make this script generic
        include_option = '-si'
        script_file = (
            sys.executable
            if getattr(sys, 'frozen', False)
            else os.path.realpath(__file__)
        )
        current_dir = os.path.dirname(script_file)
        parent_dir = os.path.dirname(current_dir)
        cct_top_dir = os.path.dirname(os.path.dirname(parent_dir))
        config_dir = Path(__file__).parent.parent.parent.parent.parent
        cct_file = os.path.realpath(sys.argv[1])
        cip_file_name = os.path.splitext(os.path.basename(cct_file))[0]
        cct_header_data = _parse_cct(cct_file)
        additional_includes = cct_header_data['ADDITIONAL_INCLUDES']
        stub_dir = os.path.join(cct_top_dir, additional_includes)
        with open(
            os.path.join(config_dir, 'cip', cip_file_name + '.cip'), 'w'
        ) as cip_file:
            print("* suppress messages", file=cip_file)
            print('-q', stub_dir, file=cip_file)
            paths = []
            added_directories = []
            force_include_files = []

            walk_results = list(os.walk(stub_dir))
            # Sort by directory
            walk_results.sort(key=lambda x: x[0])

            for d, ds, fs in walk_results:
                if d.endswith('prlforceinclude'):
                    for fn in sorted(fs):
                        force_include_files.append(os.path.join(d, fn))
                else:
                    short_name = _add_directory(d, fs, ds, stub_dir, added_directories)
                    if short_name:
                        done = False
                        # insert stub immediately before corresponding path so that order
                        # is correct for include_next
                        for i in range(len(paths)):
                            if not done and os.path.basename(paths[i]) == os.path.basename(
                                d
                            ):
                                paths.insert(i, d)
                                added_directories.append(short_name)
                                done = True
                        if not done:
                            paths.insert(0, d)
                            added_directories.append(short_name)
            print("* include paths", file=cip_file)
            # First go through system header files and insert Stub before related include folder. Used by Tasking CCT generator.
            system_includes = _read_syshdr(stub_dir)
            written_paths = []
            for system_include in system_includes:
                matching_stub = _find_stub_header(
                    paths, os.path.basename(system_include)
                )
                if matching_stub:
                    print(include_option, matching_stub, file=cip_file)
                    written_paths.append(matching_stub)
                quoted_path = '"' + system_include + '"'
                print('-q', quoted_path, file=cip_file)
                print(include_option, quoted_path, file=cip_file)

            # Now write stub files.
            for p in paths:
                if p not in written_paths:
                    print(include_option, p, file=cip_file)

            # Paths are set, now write force include files.
            print("* force include files", file=cip_file)
            for include in force_include_files:
                print('-fi', include, file=cip_file)

    except IOError as e:
        print("IO ERROR " + str(e))


if __name__ == "__main__":
    add_stub_and_syshdr_includes()
