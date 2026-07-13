# Corpus Placement

Place the operator-approved source documents under:

`corpus/source/`

Do not include application code here.

Recommended ingestion metadata:
- source ID;
- title;
- author;
- edition/date;
- file name;
- page or location;
- chunk ID;
- checksum;
- ingestion version.

The new implementation must create its own clean index from these sources unless the operator explicitly authorizes reuse of an existing index.
