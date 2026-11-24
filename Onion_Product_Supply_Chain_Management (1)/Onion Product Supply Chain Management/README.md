# Onion Product Supply Chain Management Across All States

Onion Product Supply Chain Management Across All States is an educational prototype for onion-batch traceability across Indian states, paired with All-India onion market observations from AGMARKNET.

## What is included

- Python blockchain with SHA-256 hash-linked blocks and chain validation.
- Ed25519 transaction signatures and role-based permissions.
- Onion batch creation, custody transfers, delivery events, splitting and merging.
- Parent-child batch lineage and batch-history lookup.
- SQLite persistence for blocks, transactions, actors, batches, lineage and market observations.
- Streamlit pages for dashboard, market analytics, batch management, supply-chain events, split/merge, blockchain explorer, QR lookup and multi-layer tampering audit.
- Tampering audit checks block hashes and previous-hash links, Ed25519 transaction signatures, actor role permissions, and consistency between blockchain transactions, batch snapshots, batch lineage and the SQLite transaction index. New operations are blocked if this persisted audit fails. See `TAMPER_DETECTION_ENHANCEMENT.md` for the demonstration guide and limitations.
- Original uploaded AGMARKNET CSV, processed All-India onion CSV, provenance metadata and the original notebook as a reference.

## Important data distinction

The included AGMARKNET source file contains 18,083 market observations across ten columns. Filtering the supplied snapshot to `Commodity == Onion` yields 583 rows, 25 reported state labels, 537 markets and one arrival date (18 November 2026). The records are real market-price observations, not farm-to-retail batch histories. The application labels all prototype batch events as `DEMO`. This supplied snapshot is not a 12-month historical series.

AGMARKNET price fields are treated as INR per quintal. The exact source schema is normalized by `scripts/prepare_market_data.py`.

## Requirements

- Windows 10/11
- Python 3.11 or newer
- VS Code (optional) and a web browser

## Setup (PowerShell)

Open a terminal in the extracted `Onion Product Supply Chain Management` folder.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks environment activation, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Prepare the market dataset

The original source is included at:

`data/official/raw/agmarknet_original.csv`

Run:

```powershell
python scripts/prepare_market_data.py
```

This writes:

- `data/official/processed/all_india_onion_data.csv`
- `data/official/processed/invalid_onion_rows.csv` (only rows requiring review)
- `data/metadata/source_metadata.json`

The preprocessing script standardizes column names, filters onion records, parses arrival dates, converts prices to numeric values, removes exact duplicates, and separates rows failing required-field or price-range checks. It does not invent missing historical records.

## Initialize database and demo actors

```powershell
python scripts/initialize_database.py
```

This creates `database/agritrace.db`, the genesis block, and the five demo participants if they do not already exist. It also imports the processed market rows.

## Run the Streamlit application

```powershell
streamlit run app.py
```

The browser should open at `http://localhost:8501`.

## Demo participants

| Actor ID | Role and split/merge permissions |
|---|---|
| `farmer_001` | FARMER — can split/merge while the current holder |
| `center_001` | COLLECTION_CENTER — can split/merge while the current holder |
| `transporter_001` | TRANSPORTER — cannot split/merge |
| `wholesaler_001` | WHOLESALER — can split/merge while the current holder |
| `retailer_001` | RETAILER — cannot split/merge |

The UI uses these demo actors for signed operations. This is a controlled college prototype, not a production identity-management system.

## Private key warning

On first startup, local Ed25519 private keys are generated under `data/keys/`. They are stored as unencrypted local PEM files to keep this classroom prototype simple. Keep this folder private, do not upload it to GitHub, and do not distribute the ZIP after running the app if it contains private keys. The `.gitignore` excludes private PEM files. For a production system, use encrypted key storage or a hardware-backed key manager and real participant authentication.

If you delete the local private key files after transactions have been signed, the app will generate new keys for those actor IDs. Existing block hashes remain verifiable, but old signatures will no longer be verifiable with the replacement public keys. Back up the keys securely.

## Tests

```powershell
pytest -q
```

## Project structure

```text
Onion Product Supply Chain Management/
├── app.py
├── config.py
├── requirements.txt
├── agritrace/
│   ├── blockchain.py
│   ├── security.py
│   ├── database.py
│   ├── market_data.py
│   ├── service.py
│   ├── bootstrap.py
│   └── ui_helpers.py
├── pages/
│   ├── 1_Market_Analytics.py
│   ├── 2_Batch_Management.py
│   ├── 3_Supply_Chain_Tracking.py
│   ├── 4_Batch_Operations.py
│   ├── 5_Blockchain_Explorer.py
│   ├── 6_QR_Verification.py
│   └── 7_Tampering_Detection.py
├── database/
├── data/
├── generated/qr_codes/
├── notebooks/reference/Untitled-1_original.ipynb
├── scripts/
└── tests/
```

## Prototype limitations

- The blockchain is a local, single-node hash-linked ledger. It does not implement distributed consensus or a multi-machine validator network.
- Tampering checks can identify altered stored blocks, broken hash links, invalid transaction signatures and mismatches in the SQL transaction index. However, without an independent external checkpoint or distributed network, a complete deletion of the newest blocks or replacement of the entire local database cannot be conclusively detected.
- Role checks are application-level permissions for a demo; the UI is not protected by production login/authentication.
- QR codes identify a batch for lookup in this local application. They are not public URLs and do not independently prove physical product authenticity.
- Market prices and batch traceability are separate data streams. A market observation is not proof of a particular batch's origin or journey.
- Split/merge operations preserve parent-child identifiers and quantities in the prototype database; commercial-grade chain-of-custody validation requires additional operational controls.

## Reference notebook

`notebooks/reference/Untitled-1_original.ipynb` is included unchanged as a record of the original notebook work. The runnable application is the modular code described above.


### Split and merge permissions

Batch splitting and merging are permitted for `FARMER`, `COLLECTION_CENTER` and `WHOLESALER` roles, but only when the participant is the current holder of the relevant active batch(es). `TRANSPORTER` and `RETAILER` roles cannot perform split/merge operations. The service validates both role permission and current-holder ownership before recording the operation.
