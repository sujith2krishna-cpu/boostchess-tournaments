# India place list (LGD)

`1-state.csv`, `2-district.csv` and `3-subdistrict.csv` are copies of
`administrative/1-state.csv`, `2-district.csv` and `3-subdistrict.csv` from
<https://github.com/planemad/india-local-government-directory> (commit `6d3d839`), a mirror of the
**Local Government Directory (LGD)**, Ministry of Panchayati Raj, Government of India
(<https://lgdirectory.gov.in/downloadDirectory.do>; the mirror retrieved them on 11 March 2022).

Licence: **Government Open Data License - India**
(<https://data.gov.in/government-open-data-license-india>). Attribution: "Local Government
Directory, Ministry of Panchayati Raj, Government of India". The data providers do not endorse
this project, and the data comes with no warranty.

The files are kept here unchanged so that nothing is fetched by the daily run. `scripts/places.py`
reads them to fill an empty state (see the README, "How a missing state is filled"). Newer
districts (created after March 2022) are not in them.
