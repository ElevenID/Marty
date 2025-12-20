# Migration Status: Jinja2 to React

## Completed Tasks
- [x] **Backend Refactoring**:
    - Converted `src/marty_plugin/legacy_apps/apps/ui_app/main.py` to a pure JSON API.
    - Verified `src/marty_plugin/legacy_apps/apps/verifier_api.py` is a pure JSON API.
    - Implemented `DummyTemplates` hack in `src/marty_plugin/legacy_apps/ui_app/app.py` to return JSON instead of rendering templates (legacy support).
    - Removed `templates` directory.
- [x] **Frontend Development**:
    - Created new React components:
        - `AdminDashboard.js`
        - `PassportDemo.js`
        - `CscaManager.js`
        - `PkdManager.js`
        - `TrustAnchor.js`
        - `MetricsViewer.js`
    - Updated `Navigation.js` to include the "Admin" section.
    - Updated `App.js` with routes for all new components.
    - Added `recharts` for metrics visualization.
- [x] **Build Verification**:
    - Successfully built the React application (`npm run build`).
- [x] **API Integration**:
    - Connected React components to backend endpoints.
    - Implemented specific admin endpoints in `main.py` (CSCA, PKD, Trust Anchor management).

## Pending Tasks
- [ ] **Testing**:
    - End-to-end testing of the new Admin flows.

## Next Steps
1.  **Run the Application**: Start the backend and frontend to verify functionality in a running environment.
2.  **End-to-End Testing**: Perform manual or automated tests to ensure the Admin features work as expected.
