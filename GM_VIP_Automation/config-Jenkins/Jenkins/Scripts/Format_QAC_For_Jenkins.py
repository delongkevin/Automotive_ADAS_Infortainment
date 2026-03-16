"""
This script is used to format our QAC violations from the RCR report into a format that Jenkins can read.

Without the proper QAC CI license, we can't read the line number, so they are spoofed as increasing integers.
"""

r""" New Parser 
// Reference - https://github.com/jenkinsci/warnings-ng-plugin/blob/main/doc/Documentation.md#creating-a-groovy-parser-programmatically

// Some Name - QAC Result Parser - Custom
// ID - QACustom
// Regex - ^(.+?)\((\d+),(\d+)\): (Err|Msg)\((\S+):(\S+)\) (.+?)$
// Example Log Message - C:\usr_tmp\8068503f\sw\platform\SFR\TC4DxA\IfxClock_regdef.h(32,6): Msg(Normal:REQUIRED) [U] The identifier '%1s' is reserved for use by the library.
// Mapping Script - 
import edu.hm.hafner.analysis.Severity

String   fileName = matcher.group(1)
Integer  lineNumber = Integer.parseInt(matcher.group(2))
Integer  columnNumber = Integer.parseInt(matcher.group(3))
String   type = matcher.group(4)
String   reportedSeverity = matcher.group(5)
String   category = matcher.group(6)
String   message = matcher.group(7)


Severity severity
switch (type?.toLowerCase()) {
    case 'err': severity = Severity.ERROR; break
    default:
        switch (reportedSeverity?.toLowerCase()) {
            case 'low': severity = Severity.WARNING_LOW; break
            case 'normal': severity = Severity.WARNING_NORMAL; break
            case 'high': severity = Severity.WARNING_HIGH; break
            default: severity = Severity.WARNING_NORMAL
        }
}

// Option to add .setType
return builder.setFileName(fileName)
    .setLineStart(lineNumber)
    .setColumnStart(columnNumber )
    .setCategory(category)
    .setMessage(message)
    .setSeverity(severity)
    .buildOptional()
"""

import argparse
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

import git

repo = git.Repo(".", search_parent_directories=True)
_rev_parse = repo.git.rev_parse("--show-superproject-working-tree").strip()
project_root = Path(_rev_parse or repo.working_tree_dir)

top_level_folders = [f.name for f in project_root.iterdir() if f.is_dir()]

parser = argparse.ArgumentParser(description='QAC Project Type')
parser.add_argument('report_dir', type=str, help='The Report Directory for your QAC project')
parser.add_argument('--new_parser', type=bool, help='The new parser for the QAC project for Jenkins recordIssue', default=True)
args = parser.parse_args()

warning_set = set()  # Used to suppress duplicate console warnings


def find_project_root(path) -> str:
    file_as_path = Path(path)
    # if file_as_path.is_absolute():
    #     return file_as_path.__str__()
    for top_level_folder in top_level_folders:
        if top_level_folder in path:
            return top_level_folder + path.split(top_level_folder, maxsplit=1)[-1]
    warning_msg = f"Could not find project root for {path}."
    if warning_msg not in warning_set:
        logger.warning(warning_msg)
        warning_set.add(warning_msg)
    return path


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def rule_group_to_name(rulegroup: str) -> str:
    rulegroup_lower = rulegroup.lower()
    if any(keyword in rulegroup_lower for keyword in ('m3cm', 'misra')):
        return 'MISRAC'
    if any(keyword in rulegroup_lower for keyword in ('certccm', 'certc')):
        return 'CERTC'
    logger.warning(f"Could not find rule group '{rulegroup}', talk to your integrator and update {__file__}")
    return rulegroup.upper()


def rule_enforcement_to_severity(rule: str) -> tuple[str, str]:
    rule_lower = rule.lower()
    severity_map = {
        'm3cm-3': ('Low', 'ADVISORY'),
        'advisory': ('Low', 'ADVISORY'),
        'm3cm-2': ('Normal', 'REQUIRED'),
        'required': ('Normal', 'REQUIRED'),
        'm3cm-1': ('High', 'MANDATORY'),
        'mandatory': ('High', 'MANDATORY'),
        'rule': ('Normal', 'RULE'),
        'recommended': ('Low', 'RECOMMENDED'),
        'requested': ('Normal', 'REQUESTED'),
    }

    for key, value in severity_map.items():
        if key in rule_lower:
            return value
    logger.warning(f"Could not find rule enforcement for rule '{rule}', talk to your integrator and update {__file__}")
    return 'Normal', rule.upper()


IGNORED_MESSAGES = {
    1281,  # Integer literal constant is of an unsigned type but does not include a "U" suffix.
    2986,  # This operation is redundant. The value of the result is always that of the right-hand operand
    4424,  # An expression of 'essentially enum' type (%1s) is being converted to unsigned type, '%2s' on assignment.
}  # Some QAC messages are inconsistently reported.   Silencing these for CI such that rejections can be reliably made.

IGNORED_FILES = {
    'VMemTst.c',
    'vHsm_Core.h',
    'MemAcc.c',
}  # Some messages are generally consistent except some files.  These files we are explicitly excepting.  Only for external code.

# File paths
file_rule_compliance_report = project_root / f'{args.report_dir}/results_data.xml'
violations_file = file_rule_compliance_report.parent / 'violations.log'
stats_file = file_rule_compliance_report.parent / 'metrics.json'


def main():
    Violations = set()
    Totals = dict()

    rule_compliance_report = ET.parse(file_rule_compliance_report)
    root = rule_compliance_report.getroot()

    per_file = root.find(".//dataroot[@type='per-file']")

    rcr_files = per_file.findall('File')

    for src_file in rcr_files:
        thisFile = find_project_root(src_file.attrib['path'])
        # if thisFile is None:
        #     logger.warning(f"Could not find project root for {src_file.attrib['path']}")
        #     continue

        ruleGroups = src_file.findall('.//RuleGroup')
        for ruleGroup in ruleGroups:
            ruleGroupName = rule_group_to_name(ruleGroup.attrib['name'])
            rules = ruleGroup.findall('Rule')
            for rule in rules:
                severity, enforcement_name = rule_enforcement_to_severity(rule.attrib['id'])
                messages = rule.findall('.//Message')
                for message in messages:
                    guid = message.attrib['guid']
                    text = message.attrib['text']
                    activeCount = int(message.attrib['active'])
                    msgId, details = text.split('. ', maxsplit=1)
                    # category
                    severity = severity if args.new_parser else '1'

                    compliance_identifier = f"{ruleGroupName}-{enforcement_name}"
                    category = msgId if not args.new_parser else compliance_identifier
                    if not int(msgId) in IGNORED_MESSAGES:
                        if not any(ignored_file in thisFile for ignored_file in IGNORED_FILES):
                            Violations.add((thisFile, severity, category, details, activeCount))

                    Totals[compliance_identifier] = Totals.get(compliance_identifier, 0) + int(activeCount)

    with open(violations_file, 'w') as f:
        Violations = sorted(Violations)
        for message in Violations:
            thisFile = message[0]
            severity = message[1]
            category = message[2]
            details = message[3]
            activeCount = int(message[4])

            for i in range(activeCount):
                # Err - Error, Msg - Warning
                f.write(f"{thisFile}({i},0): Msg({severity}:{category}) {details}\n")

    with open(stats_file, 'w') as f:
        QAC_Totals = {f"QAC_{key}": value for key, value in Totals.items()}
        json.dump(QAC_Totals, f, indent=4)


if __name__ == "__main__":
    main()
