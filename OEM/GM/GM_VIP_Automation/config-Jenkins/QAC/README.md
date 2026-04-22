# Helix QAC Setup and Execution Guide

Helix QAC is a static code analysis tool used for software development. It helps identify programming errors and compliance issues in C and C++ code. QAC ensures coding standards and best practices, leading to high-quality and maintainable code.

<!-- TOC -->
* [Helix QAC Setup and Execution Guide](#helix-qac-setup-and-execution-guide)
  * [Installation](#installation)
    * [License](#license)
  * [QAC Usage (GUI)](#qac-usage-gui)
    * [Synchronization](#synchronization)
    * [Compiler Configuration Template (CCT) import](#compiler-configuration-template-cct-import)
    * [General Usage](#general-usage)
  * [Project Requirements](#project-requirements)
  * [QAC Analysis Results and Suppressions](#qac-analysis-results-and-suppressions)
    * [Required to Fix:](#required-to-fix)
    * [Message Levels:](#message-levels)
    * [Rule Groups:](#rule-groups)
    * [Severity Levels:](#severity-levels)
    * [Suppressions](#suppressions)
      * [QAC-Deviation Approval Process](#qac-deviation-approval-process)
      * [Suppression Types](#suppression-types)
  * [QAV](#qav)
  * [CI/CD Integration](#cicd-integration)
  * [Project Setup and Configuration, Extra Considerations](#project-setup-and-configuration-extra-considerations)
    * [Project Creation](#project-creation)
    * [CCT Setup](#cct-setup)
    * [Compliance Modules and the Rule Configuration File](#compliance-modules-and-the-rule-configuration-file)
    * [.gitignore](#gitignore)
  * [Files and Folders to note.](#files-and-folders-to-note)
  * [FAQ](#faq)
<!-- TOC -->

-----------------

## Installation

Fetch and install the Helix QAC setup and necessary compliance modules from our [JFrog Artifactory](https://elc-jfrog.magna.global/ui/repos/tree/General/sw-d2h7510-raw-dev-local%2FTools%2FInstallers%2FQAC%2F2024.4) location, and install it to the system.
If you're running Linux, there is a missing dependency `libxcb-xinput0` that will also need to be installed.

It is highly advisable that the project uses the latest version of Helix QAC that is released and licensed by the time of the project setup.

### License

To get a license for QAC, you'll need to raise a [GEED Ticket](https://elc-geed.magna.global/). The license is
bound only to your username `whoami`.

1. Open the Helix GUI found at `<QAC_Install_Path>/Helix-QAC-<version>/common/bin/qagui`
2. Import the license. Make sure the license supports all the required compliance modules.
    1. The License Server and Port will be included in the email the license is communicated in.
    2. If you don't yet have a QAC license, please request by submitting a [GEED](https://elc-geed.magna.global/home.php) ticket.
    3. __Be aware that the username of the system must match your MAGNA short username regardless of what you've submitted for the GEED ticket.__


-----------------

## QAC Usage (GUI)

### Synchronization

Once the project has a QAC project set up, executing QAC as a developer is quite simple. From person to person, the most that's likely to change is the contents and locations which is handled via `synchronization`, found at `Project -> Synchronize`.
There are multiple "synchronization" options, with the key ones listed below.
- `Process Compilation Database` - With `compile_commands.json`, QAC identifies the project files.  This relies on your project being able to create this file, but is **much much** faster.
- `Process Injection/Monitor` - You have QAC build your application, and monitor the process to identify how your binary(s) was built.

Generally, you won't need to re-synchronize the project unless files unless source files have been moved/added/removed.

### Compiler Configuration Template (CCT) import

While not strictly required, it is advisable that you import your project's generated CCT file which is located in the QAC config folder i.e. `*/prqa/configs/Initial/config`). Without doing this, the CCT selected will be reset to an invalid default when you next save the project settings.


### General Usage

Navigating/Cleaning/Analyzing within the GUI is outside the scope of this document, but is simple and intuitive enough that reaching out to a colleague should suffice if you're stuck.

-----------------

## Project Requirements

The configured QAC project's Rule Configuration File (rcf) is per GM's [CYS4000](https://codebeamer.magna.global/cb/tracker/147415764)

## QAC Analysis Results and Suppressions

QAC is largely used to ensure compliance to an existing standard such as [MISRA C](https://misra.org.uk/).

### Required to Fix:

For each project, the rules and standards to follow are provided as customer requirements. If these standards are not available at the project's outset, default to `MISRA-C` and `CERT-C` (or their C++ equivalents) as a minimum.

Standards typically specify which rules must be followed. For instance, `MISRA Mandatory` rules are obligatory; deviations from `MISRA Document` rules must be documented, reasoned, and approved; and `MISRA Advisory` rules must be considered but can be ignored if necessary.  As such, if no guidance is given, default to the rulesets' required rules.  Showing only the higher criticality items allows for better prioritization.

Note: You must link to the requirements baseline, dated, and update the configuration the ensure alignment. Please do so below

| Baseline Link | QAC Config Date | Notes       |
|---------------|-----------------|-------------|
| [TODO]()      | 1999-01-01      | Brief Notes |

### Message Levels:

There are two levels of messages that need to be considered for your QAC project: Errors and Warnings. Errors are the most severe and **must** be resolved. Quite often their existence will prevent the complete analysis. Warnings are less severe and should be resolved if possible, but can be suppressed iff necessary (and permitted).

### Rule Groups:

Each compliance module, e.g. `M3CM`, has sets of rules sorted into different categories. While the naming of these categories may sometimes imply the significance of each rule contained, such as `MISRA Advisory` vs `MISRA Mandatory`, there is no system built into QAC actually giving these weight/importance over each-other.

### Severity Levels:

Each message is assigned a severity level from `0-9` where the higher the level, the more important the message is. However, as "severity" is subjective, you may notice misalignment a message's rulesgroup(s) and its severity level. For example, the `MISRA Required` rule group may be reporting a message of severity level 1 whereas `MISRA Advisory` may be reporting messages of severity level 6.

Some projects use the QAC classification of `Severity` of `0-9` to determine which issues must be resolved. This comes from a misunderstanding/confusion of the QAC rule categories also originally being `0-9`. If local management is dictating severity be checked against, pushback should be made.

### Suppressions

#### QAC-Deviation Approval Process

L2H7890_Software Suppression and Deviation Process.


#### Note: This section is a draft, submitted early as this will very soon need to be pointed to.

In each feature module, it's common to have the folders `inc`, `src`, `doc`, etc.  In the `doc` folder, create a file named `staticanalysis_supressions.csv` in the the form of

| ID           | File     | Message ID | Message Text                                                                                                            | Author Justification | CCB Remarks                           |
|--------------|----------|------------|-------------------------------------------------------------------------------------------------------------------------|----------------------|---------------------------------------|
| myFile_0001  | myFile.c | 1881       | The operands of this equality operator are expressions of different 'essential type' categories (unsigned and Boolean). | TODO                 | (optional) remarks from the reviewers |
| myFile_0002  | myFile.c | 0310       | Casting to different object pointer type.                                                                               | TODO                 | (optional) remarks from the reviewers |

On the suppression line, add an additional comment for the ID associated with it.  For multiple suppressions in the same line, comma separate them.  For example
```C
result = result | Smu_ActivateRunState(HwUnit, SMU_SAFE_SSM0); /*PRQA S 1881 */ /* Suppression UID: #0001,#0002 */
```


#### Suppression Types

This subsection serves as a concise overview of various suppression types, **without** implying approval or outlining the process for approval for any specific one.

While resolving all QAC reported issues down to zero may seem like an obvious goal, it isn't generally feasible, and suppression of the warnings (not errors) might be used for violations that aren't to be resolved. There are four levels of suppression to consider:

1. **Line(s) Suppression**: If a specific warning needs to be suppressed.
    * Single line with an inline comment: `/* PRQA S 0388 */ /* Suppression UID: #0001 */`
    * Multiple lines:
         ```C
         /* PRQA S <warning_number> ++ */  /* Suppression UID: #0001 */
         /* ...Code that triggers warning... */
         /* PRQA S <warning_number> -- */
         ```
        - This is generally discouraged, discouraged, but allowed if it makes sense. Suppressing over multiple lines may suppress valid warnings that should be resolved instead.
2. **File Suppression**: If applicable, QAC warnings can be suppressed for the remainder of a file with an in-line comment e.g. `/* PRQA S 0388  EOF */ /* Suppression UID: #0001 */`
    - This is **highly** discouraged and must be approved by [CCB](#qac-deviation-approval-process).
3. **Project Suppression**: Each project should have an authority or group to discuss and decide on the suppressions to be made project-wide. These suppressions are selected within the rcf (Rules Configuration File) file; the `Rule Configuration` tab of the `Project Properties` window of the QAC GUI.
4. **Global Suppression**: Global suppressions are any rules to be disabled for all projects within Magna Electronics. At the time of writing, there are none found within the GPEP process documents. Like with Project Suppressions, these are disabled by the rcf file.


-----------------

## QAV

Besides using QAC's GUI, there are two main methods to observe the results of the analysis in detail. The first is to generate an enhanced report with qacli, which Magna Electronics doesn't currently supply a license for. The other is to use the [QAV Dashboard](http://eahmsqav10.magna.global:8080) which requires an additional [GEED](https://elc-geed.magna.global/home.php) request

QAV is largely a management dashboard/tool and is not so useful for the average developer. As such, reports are usually only uploaded for the mainline branch(es) at a potentially reduced frequency as part of the CI/CD pipeline.

-----------------

## CI/CD Integration

-----------------

## Project Setup and Configuration, Extra Considerations

__This section should only be considered if you're setting up a new QAC configuration for the project, not for the average user/developer.__

### Project Creation

Project setup is quite simple.

1. `Project --> Create New Project`
    * Enter the relevant details. Name/Location etc.
    * `Next`
2. Select the compiler for each CCT required.
    * Unless otherwise required, select `Auto_generate_<language>`.
    * `Next`
3. `Finish`

### CCT Setup

The CCT (Compiler Configuration Template) is used to define the compiler specific values, intrinsics, behaviours, etc. Previously, this was a point of difficulty, but now simple with the below steps:

1. `Project --> Synchonize...`
2. Select Sync Type `Process Injection`
3. Enter your build command.
4. Select `Generate CCT` (and `Optimize Project`)
5. Press `Synchronize`

### Compliance Modules and the Rule Configuration File

Please refer to [CYS4000](https://codebeamer.magna.global/cb/tracker/147415764)

### .gitignore

Be sure to create and commit a `.gitignore` file to avoid repository confusion and clutter. Below is a default one for a QAC project

```.gitignore
# Generated Items
cip/
logs/
output/
reports/
*.stamp
*.status
*lock
*.hash
```

-----------------

## Files and Folders to note.

Largely, you should feel free to ignore all the files/folders within the QAC project config, deferring to use [QAC's](https://www.perforce.com/products/helix-qac) GUI. However, here is a brief overview of the most important files/folders.

* `<project-name>`
    * prqaproject.xml - The file holding the project information, including all the associated source files.
    * prqa/
        * qa-framework-app.xml - This file includes retained dialog information such as for `synchronize`. The project may want to leave a convenient default.
        * configs/<config-name>/config/
            * *.acf - Holds the information for all assigned compliance modules and their versions
            * *.rcf - The project/config file defining the rules to be checked. This is usually a summation of the default rules for the decided compliance modules +/- project specific decisions.

-----------------

## FAQ

1. Q: Why is this README written instead of us going to the official Magna documentation in GPEP?
    * A: GPEP_5_1 is *slightly* lacking when it comes to its completeness. Here are the links for pages that contain "QAC":
      [1](http://eahmswebsrv01/gpep_5_1/index.htm?goto=6:2591),
      [2](http://eahmswebsrv01/gpep_5_1/index.htm?goto=6:2608),
      [3](http://eahmswebsrv01/gpep_5_1/index.htm?goto=2:10:1583),
      [4](http://eahmswebsrv01/gpep_5_1/index.htm?goto=2:10:1582),
      [5](http://eahmswebsrv01/gpep_5_1/index.htm?goto=2:10:1585).
    * A: GPEP_6, as of writing, has the same lackings as GPEP_5_1.
2. Q: After resolving a QAC issue, a new one(s) appeared. Why?
    * A: A couple of things can cause this
        1. The solution to the warning is also a violation. There are cases where the only valid solution(s) are also warnings.
        2. An error may prematurely stop a file analysis. Resolving the issue may permit QAC to find the remaining issues.
3. Q: Why are we using *this* version of QAC?
    * A: This is the version that we readily had the installation files for at the time of setup. Migrating mid-project to a newer version is generally not worth the effort without a specific need.
4. Q: Where are the HIS metric thresholds derived from?
    * A: `TODO: Link to HIS Metric Threshold derivation document.`
5. Q: Sections of the code aren't owned by us, but have a large number of violations.  What do we do?
    * A: In the QAC configuration, you're able to provide attributes to different folders.  If your project is organized well, you can set the `external` flag to the external and 3rd-party folders.

-----------------
