;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
; 29 Oct 21 - Richard Woodruff - Adapt from J7ES for J721S2
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

Step 1: Enter DDR information into DDR Config XLS
Step 2: Generate GEL file "J721S2-DDR-EVM-LP4-4266.gel" from XLS
Step 3: Create a new file J721S2_addr-map-offs-LP4-4266_DDR_config.gel merging J7-DDR-addr-map-offs.gel + J721S2-DDR-EVM-LP4-4266.gel + J7_DDR_config.gel
Step 4: Merge in any GEL differences from the EVM template.  Do not overwrite J7_DDR_config.gel updates /* Some gel_converter bugs depending on version none for 2.4.3 */
Step 5: Generate a CMM using the gel converter. gelconverter <filea>.gel <filea>.cmm
Step 6: Merge template CMM fixes into newly created CMM file. /* none needed for gel_converter  2.4.3, early SW-pdk usage may require some work around */
Step 7: Connect with a TRACE32 PowerView instance and run the script "run_all_ddr_test.cmm"
Step 8: If the A72 memtester starts, enter a buffer base address of 0x81000000 with a size suitable for testing.

