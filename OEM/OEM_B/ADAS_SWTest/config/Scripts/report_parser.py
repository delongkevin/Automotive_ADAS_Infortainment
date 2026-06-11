from lxml import etree
import argparse
import time
from datetime import datetime
import re

def main(input_file_name, filter_file_name, create_filters):
    """
    Script to parse CANoe reports and generate the JUnit report to import it to Jenkins
    """

    input_file = etree.parse(input_file_name, parser=etree.XMLParser(remove_blank_text=True))
    if filter_file_name:
        testinfo_file = etree.parse(filter_file_name, parser=etree.XMLParser(remove_blank_text=True))
    else:
        testinfo_file = etree.Element("empty")

    testsuite_start_timestamp = float(input_file.getroot().attrib['timestamp'])
    testsuite_end_timestamp = float(input_file.getroot().xpath('./verdict')[0].attrib['timestamp'])
    report = etree.Element("testsuite")
    print("report :",report)
    testsuite_name = input_file.xpath('//description[../name[text()="Test Module Name"]] | //description[../name[text()="Test Unit"]] | //description[../name[text()="Test Configuration"]]')[0].text
    report.set('name', testsuite_name)
    
    report.set('time', str(testsuite_end_timestamp - testsuite_start_timestamp))
    test_number = 0
    test_failed = 0
    test_errors = 0
    if create_filters:
        filters = etree.Element("testsuite")
        filters.set('name', testsuite_name)
    
    for group_child in input_file.xpath('//testcase'):
        test_number += 1
        new_testcase = etree.Element("testcase")
        testcase_name = group_child.xpath('./title')[0].text
        new_testcase.set('name', testcase_name)
        
        testcase_start_timestamp = float(group_child.attrib['timestamp'])
        for testcase_child in group_child.getchildren():
            if testcase_child.tag == 'verdict':
                testcase_end_timestamp = float(testcase_child.attrib['timestamp'])
                check_test_case = False
                if testcase_child.attrib['result'] != 'pass':
                    check_test_case = True
                    error_text = 'Errors found:\n'
                    error_type = 'FAILURE'
                    for error in group_child.findall(".//teststep[@result='fail']"):
                        error_text += str(error.attrib['ident']) + ' => ' + str(error.text) + '\n'
                        if error.attrib['ident'] == 'VISION' and error.attrib.get('result') != 'pass':
                            error_type = 'VISION'

                    found = testinfo_file.xpath('//testsuite[@name="%s"]/testcase[@name="%s"]' % (testsuite_name, testcase_name))

                    if len(found):
                        for ticket in found[0].xpath('./ticket[@status!="closed"]'):
                            for error in ticket.xpath('error'):
                                if error.text == error_text:
                                    error_type == 'FILTERED'
                                    check_test_case = False
                            for regex in ticket.xpath('regex'):
                                x = re.search(regex.text, error_text)
                                if x is not None:
                                    error_type == 'FILTERED'
                                    check_test_case = False

                    if error_type == 'VISION':
                        test_errors += 1
                        error_node = etree.Element("error")
                    else:
                        test_failed += 1
                        error_node = etree.Element("failure")
                    error_node.text = error_text
                    new_testcase.append(error_node)
                    
                if create_filters == 2 or (create_filters == 1 and check_test_case):
                    filter_testcase = etree.Element("testcase")
                    filter_testcase.set('name', testcase_name)
                    ticket_node = etree.Element("ticket")
                    ticket_node.set('name', 'INITIAL_FILTER')
                    regex_node = etree.Element("regex")
                    regex_node.text='.*'
                    ticket_node.append(regex_node)
                    filter_testcase.append(ticket_node)
                    filters.append(filter_testcase)

        new_testcase.set('time', str(testcase_end_timestamp - testcase_start_timestamp))
        report.append(new_testcase)


    report.set('tests', str(test_number))
    report.set('failures', str(test_failed))
    report.set('errors', str(test_errors))
    if test_number:
        with open(input_file_name[:-4] + '_Jenkins.xml', "w", encoding='utf-8') as output_file:
            output_file.write(etree.tostring(report, pretty_print=True, encoding='unicode'))
        if create_filters:
            with open(input_file_name[:-4] + '_Jenkins_Filters.xml', "w", encoding='utf-8') as output_file:
                output_file.write(etree.tostring(filters, pretty_print=True, encoding='unicode'))
    else:
        print('No test available')

if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(description='Script to parse CANoe reports and generate the JUnit report to import it to Jenkins.')
    PARSER.add_argument("input_file_name", metavar="input_file_name", help='Input file')
    PARSER.add_argument('-f', "--filter", metavar="filter_file_name", help='Test info file')
    PARSER.add_argument('-cf', '--create_filters', action='store_true', help='Create filter file for all errors')
    PARSER.add_argument('-af', '--create_all_filters', action='store_true', help='Create filter file for all test')

    ARGS = PARSER.parse_args()

    main(ARGS.input_file_name, ARGS.filter, 2 if ARGS.create_all_filters else 1 if ARGS.create_filters else 0)