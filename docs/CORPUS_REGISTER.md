# Corpus Register

Verified: 2026-07-13. Location: `corpus/source/`. Verification performed by checksum + text-extraction audit (`pdftotext` / byte count). This register is committed; the raw source files are **not** committed (see `docs/ARCHITECTURE_DECISIONS.md`, ADR-007).

## Summary

- Files: **9**
- Duplicate checksums: **0**
- TXT: **3** · PDF: **6**
- OCR required: **none** (all files yield extractable text)
- Total extractable characters (whitespace-stripped): **≈ 4,698,274** (~1.2M tokens rough order)

## Files

| # | File | Type | Size (bytes) | Pages | Extractable chars | SHA-256 |
|---|------|------|-------------:|------:|------------------:|---------|
| 1 | Broken_Money.txt | TXT | 856,955 | — | 709,582 | `7e9d26c201f558e8ccfdb17671810914fbb3027c9abf6334c2c598aa5f9706ca` |
| 2 | Layered Money.txt | TXT | 205,927 | — | 172,631 | `c0e4b0e05ae49988a9ba3dfc88aaa2b3c1a329d344ab1eb18f8a5da1459612be` |
| 3 | The Value of a Whale.txt | TXT | 508,014 | — | 427,891 | `ac2a98a961e1d9f76354a5b1d024b8499419a8917295ce2b70a90a686840c9f2` |
| 4 | DebunkingEconomics.pdf | PDF | 5,184,601 | 498 | 1,173,756 | `e9ae8da61b2a12477f59edbb5ff11de46f3020f1954ce4bc8323ba0e53148263` |
| 5 | ErgodicInvester.pdf | PDF | 4,263,494 | 184 | 293,236 | `d498fa2a54363c116de4f3acc27004ecd5e5e2db984ccdd50636403bee202d2d` |
| 6 | Field_Investing.pdf | PDF | 1,351,885 | 14 | 18,510 | `635ef9a4b80c77a0e1786e35d359e7ea643782ef718a3ce1b2d2c9455e13f8b0` |
| 7 | Finite-and-Infinite-Games-by-James-Carse.pdf | PDF | 8,009,574 | 160 | 179,171 | `143bef992e8e5d8b1c9a7d7aa895baa8f3bc7be55a9b02cbceef12487a074354` |
| 8 | Rebuild-ELY.pdf | PDF | 17,251,142 | 512 | 994,504 | `e6cb2f8a0a0807db617e76840d3e7783542ca195752e7df7a6d207c77ae0d1ea` |
| 9 | sacred-economics-book-text.pdf | PDF | 1,782,677 | 314 | 728,993 | `7fdd27290dc477b4c20bf01f7f9c393d41768c174554c36717f31c1fc8abf48a` |

## Notes

- Files 6 (Field_Investing, 14 pp / 18k chars) and 5 (ErgodicInvester, low chars/page) are text-light; retrieval quality per source will vary — expected, not a defect.
- These are private research materials, some copyrighted. Do not publicly expose or redistribute raw text. Evidence **excerpts** may be shown inside the controlled application for traceability only.
- The retrieval module must record `source_id`, `title`, `page`/`chunk_id`, and the checksum above so evidence stays traceable to a specific, verified file.
- Any change to this set (add/remove/replace) requires re-running the checksum audit and updating this register + the vector index rebuild.
