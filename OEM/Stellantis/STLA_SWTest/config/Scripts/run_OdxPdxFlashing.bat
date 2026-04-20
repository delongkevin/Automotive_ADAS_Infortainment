@echo off
REM ********************************************************************************************
REM  $Copyright: $
REM            MAGNA Electronics - C O N F I D E N T I A L
REM            This document in its entirety is CONFIDENTIAL and may not be
REM            disclosed, disseminated or distributed to parties outside MAGNA
REM            Electronics without written permission from MAGNA Electronics.
REM

setlocal
set usecolor=1
color 0F

echo.
echo :: %date% - %time:~0,2%:%time:~3,2%:%time:~6,2%
echo.
echo ^+--------------------------------------------------^+
echo ^+           Flash PDX with OdisPdxFlasher          ^|
echo ^+--------------------------------------------------^+
echo.

Title Flash PDX
set h=%TIME:~0,2%
set m=%TIME:~3,2%
set s=%TIME:~5,2%

REM ******************************************
REM Set parameters
REM ******************************************

set "ODXPDXFLASHER=C:\prjtools\OdxPdxFlasher\v1.1.1\OdxPdxFlasher.exe"
set CURRENT_FOLDER=%~dp0
setlocal ENABLEDELAYEDEXPANSION

call :SourceExist %ODXPDXFLASHER%

set SCRIPT_PATH=%CURRENT_FOLDER%
::set TEMP_SCRIPT_PATH=%SCRIPT_PATH%
set TEMP_SCRIPT_PATH=%SCRIPT_PATH:\=\\%
set PDX_PATH=%CURRENT_FOLDER%

set OUTPUT_PDX_NAME="FL_85E907217C_X1XX_PDXVARIANT_V001_E.pdx"
set "PDX_NAME_DEFINITION=MFK5_X120_24ED6464_container"

set POWERSUPPLY_USE=1

:: set folder with the PDXs to be flashed
if "%2"=="" (
    echo "INFO: Parameter two is NOT set. To be flashed PDX has to be in the parrent-parent foldet that has to be named like the PDX itself!"
    :: set pdx name definitionaccording to the parent folder (("%~dp0..") parent parent)
    for %%i in ("%~dp0.") do set "PDX_NAME_DEFINITION=%%~nxi"
) else (
    echo "INFO: Parameter two is set. Flashed PDX from following folder: %2"
    echo.
    set PDX_PATH=%2
    for %%i in ("%2") do set "PDX_NAME_DEFINITION=%%~nxi"
)

echo PDX_PATH: %PDX_PATH%
echo PDX_NAME_DEFINITION: %PDX_NAME_DEFINITION%

:: workaround for local builds
if %PDX_NAME_DEFINITION% == container (set "PDX_NAME_DEFINITION=MFK5_X120_24ED6464_container")


pushd %PDX_PATH%
    :: user interaction
    if "%1"=="" (
        echo.
        echo "INFO: Please chose the PDX to be flashed."
        echo.
        echo  0 .  "Flash Full PDX" [**default**]
        echo  1 .  "Flash APP BTLD PDX"
        echo  2 .  "Flash BTLD PDX"
    )


    set /a count=2
    for /f tokens^=* %%i in ('where .:*.pdx') do (
        set /a count+=1
        if "%1"=="" ( echo/ !count! .  "Flash (dynamically found) %%~nxi" )
        set PDX_TO_FLASH_!count!=%%~nxi
    )

    :: chosen PDX to be flashed
    if "%1"=="" (
    echo.
    set /p choice="Please chose a PDX to be flashed: "

    ) else (set choice=%1)

    ::
    set "FLASHMODE=%choice%"
popd

REM ******************************************
REM set propper PDX names for full and app/btld
REM ******************************************
set "SW_VERSION=%PDX_NAME_DEFINITION:~5,4%"
set "SW_VERSION_EB=%PDX_NAME_DEFINITION:~12,4%"
set "OUTPUT_PDX_NAME=!OUTPUT_PDX_NAME:_X1XX_=_%SW_VERSION%_!"

:: set FULL build
set "OUTPUT_FULL_NAME=%OUTPUT_PDX_NAME:_PDXVARIANT_=__%"
if NOT exist "%PDX_PATH%\%OUTPUT_FULL_NAME%" set "OUTPUT_FULL_NAME=!OUTPUT_FULL_NAME:_%SW_VERSION%_=_%SW_VERSION_EB%_!"
:: set APP and BTLD build
set "OUTPUT_APPBLU_NAME=%OUTPUT_PDX_NAME:_PDXVARIANT_=_APPBLUDEV_%"
if NOT exist "%PDX_PATH%\%OUTPUT_APPBLU_NAME%" set "OUTPUT_APPBLU_NAME=!OUTPUT_APPBLU_NAME:_%SW_VERSION%_=_%SW_VERSION_EB%_!"
:: set BTLD build
set "OUTPUT_BLU_NAME=%OUTPUT_PDX_NAME:_PDXVARIANT_=_BLU_%"
if NOT exist "%PDX_PATH%\%OUTPUT_BLU_NAME%" set "OUTPUT_BLU_NAME=!OUTPUT_BLU_NAME:_%SW_VERSION%_=_%SW_VERSION_EB%_!"

set DYNAMIC_SELECT=1

REM ******************************************
REM Start Flashing
REM ******************************************
if '%FLASHMODE%'=='0' (
echo "INFO: FLASH PDX %OUTPUT_FULL_NAME%
set DYNAMIC_SELECT=0
::
call :StartOdisPdxFlasher %OUTPUT_FULL_NAME%
)

if '%FLASHMODE%'=='1' (
echo "INFO: FLASH PDX %OUTPUT_APPBLU_NAME%
set DYNAMIC_SELECT=0
::
call :StartOdisPdxFlasher %OUTPUT_APPBLU_NAME%
)

if '%FLASHMODE%'=='2' (
echo "INFO: FLASH PDX %OUTPUT_BLU_NAME%
set DYNAMIC_SELECT=0
::
call :StartOdisPdxFlasher %OUTPUT_BLU_NAME%
)

if %DYNAMIC_SELECT%==1 (
echo "INFO: FLASH PDX !PDX_TO_FLASH_%FLASHMODE%!
::
call :StartOdisPdxFlasher !PDX_TO_FLASH_%FLASHMODE%!
)


echo Script start at: %h%:%m%:%s%
set h=%TIME:~0,2%
set m=%TIME:~3,2%
set s=%TIME:~5,2%
echo Script ended at: %h%:%m%:%s%

echo. & echo.

if !ERRORLEVEL!==0 color 2F
exit /b 0

endlocal
goto :eof

:: param 1 PDX name
:StartOdisPdxFlasher
call :SourceExist "%PDX_PATH%\%~1"
echo %ODXPDXFLASHER% "%PDX_PATH%\%~1" 
::
call .\..\Powersupply\powersupply_ON.bat

%ODXPDXFLASHER% "%PDX_PATH%\%~1" 
call :ReturnExitcode !ERRORLEVEL!

::
call .\..\Powersupply\powersupply_OFF.bat
exit /b 0

:InstallTool
if not exist "%~1" call .\..\prepareTools.bat
if exist "%~1" EXIT /B 0
if not %usecolor%==0 color 4F
echo ERROR: Can not install %~1.
call :halt

:SourceExist
if exist %~1 exit /b 0
if not %usecolor%==0 color 4F
echo ERROR: Source is missing: %~1.
call :halt

:ReturnExitcode
echo ExitCode: %~1.
if %~1==0 exit /b 0
call .\..\Powersupply\powersupply_OFF.bat
if not %usecolor%==0 color 4F
call :halt

:: Sets the errorlevel and stops the batch immediately
:halt
call :__SetErrorLevel %1
call :__ErrorExit 2> nul
goto :eof

:__ErrorExit
rem Creates a syntax error, stops immediately
()
goto :eof

:__SetErrorLevel
exit /b %time:~-2%
goto :eof
