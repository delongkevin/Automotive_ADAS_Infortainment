import os
import re

import pyodbc

# NOTE: This script assumes that each col will have a prepending identifier matching that of the table name

mainline_branches = {
    'master',
    'develop',
    'main'
}


class DatabaseManager:
    def __init__(self):
        self.__user = os.environ['DATABASE_USER']
        self.__password = os.environ['DATABASE_PASSWORD']
        self.__branch = os.environ['BRANCH_NAME']
        self.__build_number = os.environ['BUILD_NUMBER']

        self.__server = f'tcp:zwemssqlmemswi.database.windows.net,1433'
        self.__database = f'swintegration'

        self.__context = None

        if self.__branch not in mainline_branches:
            print(f"Custom KPI uploaded only allowed mainline branch builds {mainline_branches}, but got {self.__branch}")
            exit()

    def __connect(self):
        self.__context = pyodbc.connect(
            f'DRIVER={{ODBC Driver 18 for SQL Server}};'
            f'SERVER={self.__server};'
            f'DATABASE={self.__database};'
            f'ENCRYPT=yes;'
            f'UID={self.__user};'
            f'PWD={self.__password};'
            f'TrustServerCertificate=yes;'
            f'Authentication=ActiveDirectoryPassword;'
            f'Connection;'
        )

    @staticmethod
    def __values_to_strings(value_list):
        retVals = []
        for value in value_list:
            retVals.append(DatabaseManager.__value_to_string(value))
        return retVals

    @staticmethod
    def __value_to_string(value):
        if isinstance(value, str):
            return f"'{value}'"
        elif value is None:
            return 'null'
        else:
            return str(value)

    def insert_data(self, table: str, dataDict: dict):
        if self.__context is None:
            self.__connect()

        default_dict = {
            f'Branch': self.__branch,
            f'BuildNumber': self.__build_number,
        }

        try:
            add_row_query = f"""
                INSERT INTO {self.__database}.dbo.{table} ({', '.join(default_dict.keys())})
                VALUES ({', '.join(self.__values_to_strings(default_dict.values()))})
            """
            cursor = self.__context.cursor()
            cursor.execute(add_row_query)
            print(f"Added an entry for {default_dict}")
        except pyodbc.IntegrityError:
            print(f"Entry for {default_dict} already exists")

        # add the dataDict to the same row
        update_query = f"""
            UPDATE {self.__database}.dbo.{table}
            SET {', '.join([f"{key}={self.__value_to_string(value)}" for key, value in dataDict.items()])}
            WHERE Branch = '{default_dict[f'Branch']}' AND BuildNumber = '{default_dict[f'BuildNumber']}'
        """

        cursor = self.__context.cursor()
        cursor.execute(update_query)
        self.__context.commit()

        cursor.close()

    def __exit__(self):
        if self.__context is not None:
            self.__context.close()
