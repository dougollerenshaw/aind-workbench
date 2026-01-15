# Placeholders to Fill In - BARseq Acquisition Metadata

This document lists all the missing information needed to complete the BARseq acquisition metadata files. The questions are organized by category for easy assignment to the appropriate team members.

## Quick Summary

- **Total placeholders:** 60 per acquisition file
- **Categories:** 4 (Personnel, Specimen IDs, Hardware, Timing)
- **Priority:** Hardware configuration mapping is most critical

---

## 1. Personnel Information

### Question 1.1: Who performed the acquisitions?
**For both experiments:**
- What are the full names of the experimenters who performed the BARseq imaging?
- Format: First and Last name (e.g., "Jane Smith", "John Doe")

**Current placeholder:**
```json
"experimenters": [
  "PLACEHOLDER_EXPERIMENTER_1",
  "PLACEHOLDER_EXPERIMENTER_2"
]
```

### Question 1.2: What is the IACUC protocol number?
- What is the institutional animal care and use committee protocol number for these experiments?

**Current placeholder:**
```json
"ethics_review_id": ["PLACEHOLDER_IACUC_PROTOCOL"]
```

---

## 2. Specimen Identification

### Question 2.1: What are the specimen IDs?
For each brain section that was imaged:
- **Subject 780345:** What identifier should be used for the brain section specimen?
- **Subject 780346:** What identifier should be used for the brain section specimen?

**Suggested format:** `{subject_id}_LC_section_{number}` 
- Example: "780345_LC_section_01"
- Or use existing lab naming convention

**Current placeholders:**
- Subject 780345: `"PLACEHOLDER_SPECIMEN_ID_780345"`
- Subject 780346: `"PLACEHOLDER_SPECIMEN_ID_780346"`

---

## 3. Hardware Configuration (CRITICAL)

This section requires input from someone familiar with the Dogwood microscope setup and the BARseq imaging protocol.

### Question 3.1: Which lasers are used for each DNA base?

In the Dogwood instrument, there are 7 Lumencor Celesta lasers available:
- 365nm
- 440nm
- 488nm
- 514nm
- 561nm
- 640nm
- 730nm

**For Gene & Barcode Sequencing, which laser is used for each base?**
- Base G (Guanine): Which laser wavelength? _______ nm
- Base T (Thymine): Which laser wavelength? _______ nm
- Base A (Adenine): Which laser wavelength? _______ nm
- Base C (Cytosine): Which laser wavelength? _______ nm
- DAPI: Which laser wavelength? _______ nm (likely 365nm or 440nm)

**Current placeholders:**
```
"PLACEHOLDER_LASER_G"
"PLACEHOLDER_LASER_T"
"PLACEHOLDER_LASER_A"
"PLACEHOLDER_LASER_C"
"PLACEHOLDER_LASER_DAPI"
```

### Question 3.2: What are the actual laser device names?

From the instrument JSON, the laser device names follow the pattern:
- "Lumencor Celesta 365nm"
- "Lumencor Celesta 440nm"
- etc.

Once you know which wavelengths are used (from Q3.1), the device names can be automatically filled in.

### Question 3.3: Which emission filters are used for each channel?

The Dogwood instrument has 8 emission filters (E1-E8). For each base/dye:
- Base G: Which emission filter? _______ (E1-E8)
- Base T: Which emission filter? _______ (E1-E8)
- Base A: Which emission filter? _______ (E1-E8)
- Base C: Which emission filter? _______ (E1-E8)
- DAPI: Which emission filter? _______ (E1-E8)

**Available filters from instrument:**
- E1: FF01-441/511/593/684/817 (DAPI/GFP/Red/Cy5/Cy7)
- E2: FF01-565/24 (YFP)
- E3: FF01-585/11 (RFP)
- E4: FF01-676/29 (FarRed)
- E5: FF01-775/140 (RS Cy5)
- E6: FF01-391/477/549/639/741-25 (YFP/Rs Cy5)
- E7: 69401m (DAPI/GFP/TxRed)
- E8: ZET532/640m (Alexa532/Cy5)

**Current placeholders:**
```
"PLACEHOLDER_EMISSION_FILTER_G"
"PLACEHOLDER_EMISSION_FILTER_T"
"PLACEHOLDER_EMISSION_FILTER_A"
"PLACEHOLDER_EMISSION_FILTER_C"
"PLACEHOLDER_EMISSION_FILTER_DAPI"
```

### Question 3.4: What are the emission wavelengths?

For each channel, what is the peak emission wavelength detected by the camera?
- Base G: _______ nm
- Base T: _______ nm
- Base A: _______ nm
- Base C: _______ nm
- DAPI: _______ nm (likely ~450-460nm)

**Current placeholder:** `9999` (for all channels)

### Question 3.5: What are the laser power settings?

For each laser used during acquisition:
- Base G laser: _______ mW
- Base T laser: _______ mW
- Base A laser: _______ mW
- Base C laser: _______ mW
- DAPI laser: _______ mW

**Current placeholder:** `9999.0` (for all lasers)

### Question 3.6: Hybridization probes - which fluorophores?

For the hybridization cycle, which fluorophores are conjugated to each probe?
- Probe XC2758: Which fluorophore? _______ (e.g., GFP, Alexa488, FITC, etc.)
- Probe XC2759: Which fluorophore? _______ (e.g., Cy3, Texas Red, etc.)
- Probe XC2760: Which fluorophore? _______ (e.g., Cy5, Alexa647, etc.)
- Probe YS221: Which fluorophore? _______ 

This will determine which lasers and filters are used for the hybridization channels.

**Current placeholders:**
```
"PLACEHOLDER_LASER_GFP"
"PLACEHOLDER_LASER_HYB_2"
"PLACEHOLDER_LASER_HYB_3"
"PLACEHOLDER_LASER_HYB_4"
"PLACEHOLDER_EMISSION_FILTER_GFP"
"PLACEHOLDER_EMISSION_FILTER_HYB_2"
"PLACEHOLDER_EMISSION_FILTER_HYB_3"
"PLACEHOLDER_EMISSION_FILTER_HYB_4"
```

---

## 4. Camera Settings

### Question 4.1: What was the camera exposure time?

Was the exposure time the same for all channels, or did it vary?
- If same for all: _______ ms
- If different, specify for each channel type:
  - Gene sequencing channels: _______ ms
  - Barcode sequencing channels: _______ ms
  - Hybridization channels: _______ ms
  - DAPI: _______ ms

**Current placeholder:** `9999.0` ms

---

## 5. Acquisition Timing

### Question 5.1: What were the actual acquisition times?

For each experiment, what were the approximate start and end times for each phase?

**Subject 780345 (February 19, 2025):**
- Gene sequencing started: _______ (time in HH:MM format, e.g., 09:30)
- Gene sequencing ended: _______
- Barcode sequencing started: _______
- Barcode sequencing ended: _______
- Hybridization started: _______
- Hybridization ended: _______

**Subject 780346 (June 11, 2025):**
- Gene sequencing started: _______
- Gene sequencing ended: _______
- Barcode sequencing started: _______
- Barcode sequencing ended: _______
- Hybridization started: _______
- Hybridization ended: _______

**Current placeholders:** Estimated 2-hour blocks starting at noon (clearly placeholder times)

**Note:** If exact times are not recorded, approximate durations are acceptable. For example, "gene sequencing took approximately 3 hours starting around 10am".

