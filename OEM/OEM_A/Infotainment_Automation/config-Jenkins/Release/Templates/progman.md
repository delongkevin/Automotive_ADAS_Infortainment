

# 1. Controller Global Software Issues

[//]: # (## 1.a. Hardware Block Diagram)

[//]: # (- Diagram showing relationships between CPU, RAM, flash, etc.)

[//]: # (- Short description of each block.)

[//]: # (## 1.b. Memory Map)

[//]: # (- Full memory map showing GM vs. supplier allocations.)

[//]: # (- Chip selects and flash segmentation details.)

## 1.c. RAM / ROM Utilization of HWIO package
Please refer to each `.map.xlsx` file delivered in each HWIO Package's Products folder for the breakdown of the Magna Test Software.  Else consider using the command `size <lib_name.a>` to get a breakdown of the libraries.

[//]: # (## 1.d. Memory Hardware Restrictions)
[//]: # (- i&#41; Non-checksummed areas)
[//]: # (- ii&#41; ROM with run-time updated data)
[//]: # (- iii&#41; Non-relocatable memory sections)
[//]: # (- iv&#41; Data page pointer locations)

[//]: # (## 1.e. Non-volatile Memory &#40;NVM&#41; Implementation)

[//]: # (## 1.f. Interrupt Structure)

[//]: # (## 1.g. Operating System)
[//]: # (- Supplier functions invoked before/after GM OS tasks.)

[//]: # (## 1.h. Running Reset Sources)

[//]: # (## 1.i. Watchdog Timers)

[//]: # (## 1.j. Flash Programming)

[//]: # (## 1.k. Timing Constraints)
[//]: # (- &#40;e.g., Initialization timing&#41;)

[//]: # (## 1.l. Core Access Restrictions)
[//]: # (- Cross-core access to I/O interfaces &#40;ADC, PWM, etc.&#41;)

[//]: # (## 1.m. HWIO Periodic Task Core Assignment and Utilization)

[//]: # (## 1.n. Electrical Fault Flag Operation)

[//]: # (## 1.o. Other Implementation Specific Issues)

[//]: # (## 1.p. Autosar SW Configuration Details)

# 2. Development & Instrumentation Environment Information

## 2.a. Tool Versions Used
| Tool Name    | Purpose                | Version       |
|--------------|------------------------|---------------|
| Windriver    | Compiler               | diab-5.9.9.0  |
| CMake        | Build automation tool  | 3.31.0        |
| Make         | Build system generator | 3.8.1         |
| Perforce QAC | Static code analysis   | 2024.4        |
| VectorCAST   | Unit testing           | 2024.4        |


[//]: # (## 2.b. Known Tool Chain/Component Errata)

[//]: # (## 2.c. Instrumentation System Configuration)

[//]: # (## 2.d. Tool Chain Data File Descriptions)
[//]: # (- File types, generation, usage, and purpose.)

# 3. Change Summary Between Releases

| Version | Date        | Description of Change | GM Authorization Ref |
|---------|-------------|-----------------------|----------------------|
| 0.1     | 2025/05/23  | Pre-Draft             |                      |
[//]: # (*Changes must show revision markings, inserted/deleted text, and margin change bars.*)

