# Petalcore Platform

Petalcore Platform brings the three Petalcore sites together under one website. The home page links to Index, ID, and Select.

## How it works

The Platform serves the three website pages and a shared FastAPI service. Each site uses its own API key when it requests data. Index searches the plant catalog, ID sends a photo to Pl@ntNet and displays possible matches, and Select compares a user's preferences with the catalog. The private Pl@ntNet key stays on the server.

## How to use it

Open the Petalcore Platform home page and choose a site:

- **Index** (`/index/`): search or browse the plant library, then open a plant to read more.
- **ID** (`/id/`): upload a JPG or PNG photo, choose a plant part, and view possible matches.
- **Select** (`/select/`): choose details about your space and preferences, then view suggested plants.

The photo results and Select recommendations are suggestions to help with plant discovery. They should not be treated as a certain identification or guarantee.
