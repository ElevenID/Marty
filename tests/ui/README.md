# UI End-to-End Testing Documentation

## Overview

This directory contains comprehensive end-to-end (E2E) tests for all newly created UI components in the Marty passport issuance system. The tests use Playwright with pytest to provide thorough coverage of UI functionality, workflows, and user interactions.

## Test Architecture

### Test Files Structure

```
tests/ui/
├── conftest.py                 # Pytest configuration and fixtures
├── test_new_ui_e2e.py         # Comprehensive UI component tests
├── test_advanced_workflows.py # Advanced workflow and edge case tests
├── test_smoke.py              # Quick smoke tests for basic validation
├── test_runner.py             # Test runner script with multiple options
├── setup_tests.py             # Installation and setup script
└── README.md                  # This documentation file
```

### Test Categories

1. **Smoke Tests** (`test_smoke.py`)
   - Quick validation of basic functionality
   - Page loading verification
   - Navigation testing
   - Basic form submission
   - Ideal for CI/CD pipelines

2. **Comprehensive Tests** (`test_new_ui_e2e.py`)
   - Full functionality testing for all UI components
   - Form validation and data handling
   - Tab navigation and UI interactions
   - Service-specific workflows

3. **Advanced Workflow Tests** (`test_advanced_workflows.py`)
   - Cross-service integration workflows
   - Complex form validation scenarios
   - Accessibility compliance testing
   - Performance and load testing
   - Error handling and edge cases

## Tested UI Components

### Core Services

- **CSCA Service** - Certificate authority management
- **Document Signer** - Document signing workflows
- **mDoc Engine** - Mobile document creation
- **DTC Engine** - Digital travel credential processing
- **PKD Service** - Public key directory management
- **Trust Anchor** - Certificate validation and trust management

### Enhanced Components

- **Admin UI** - System administration dashboard
- **Enhanced MDL** - Mobile driver's license processing
- **Navigation System** - Cross-service navigation testing

## Installation & Setup

### Quick Setup

```bash
# Run the automated setup script
python tests/ui/setup_tests.py
```

### Manual Setup

1. **Install Dependencies**

   ```bash
   pip install playwright pytest pytest-asyncio pytest-html pytest-xdist
   pip install uvicorn fastapi requests
   ```

2. **Install Browsers**

   ```bash
   playwright install
   # Or just Chromium for testing
   playwright install chromium
   ```

3. **Verify Installation**

   ```bash
   playwright --version
   pytest --version
   ```

## Running Tests

### Using the Test Runner (Recommended)

```bash
# Complete test suite
python tests/ui/test_runner.py

# Setup environment
python tests/ui/test_runner.py setup

# Quick smoke tests
python tests/ui/test_runner.py smoke

# Comprehensive tests only
python tests/ui/test_runner.py comprehensive

# Advanced workflow tests
python tests/ui/test_runner.py workflows

# Parallel execution (faster)
python tests/ui/test_runner.py parallel

# Generate HTML report
python tests/ui/test_runner.py report
```

### Service-Specific Testing

```bash
# Test individual services
python tests/ui/test_runner.py csca
python tests/ui/test_runner.py document-signer
python tests/ui/test_runner.py mdoc
python tests/ui/test_runner.py dtc
python tests/ui/test_runner.py pkd
python tests/ui/test_runner.py trust-anchor
python tests/ui/test_runner.py admin
python tests/ui/test_runner.py mdl
```

### Direct Pytest Commands

```bash
# All UI tests
pytest tests/ui/ -v

# Specific test file
pytest tests/ui/test_smoke.py -v

# With coverage
pytest tests/ui/ --cov=src/ui_app --cov-report=html

# Parallel execution
pytest tests/ui/ -n auto

# Generate HTML report
pytest tests/ui/ --html=reports/ui_tests.html --self-contained-html
```

## Test Configuration

### Pytest Configuration (`pytest.ini`)

Key configuration markers:

- `smoke` - Quick validation tests
- `integration` - Cross-service integration tests
- `slow` - Long-running tests
- `accessibility` - Accessibility compliance tests
- `performance` - Performance validation tests

### Browser Configuration

Tests run in headless Chromium by default with:

- 1920x1080 viewport
- 30-second timeout for actions
- Mock data enabled for consistent testing
- Security features disabled for testing

### Test Data

Mock data is provided for:

- CSCA certificates
- Passport documents
- MDL credentials
- DTC documents
- PKD entries

## Test Fixtures

### Core Fixtures (`conftest.py`)

- `ui_server` - Session-scoped FastAPI server
- `browser` - Session-scoped Playwright browser
- `page` - Function-scoped page instance
- `mobile_page` - Mobile viewport page
- `tablet_page` - Tablet viewport page

### Sample Data Fixtures

- `sample_csca_data` - CSCA certificate data
- `sample_passport_data` - Passport document data
- `sample_mdl_data` - MDL credential data
- `sample_dtc_data` - DTC document data

## Writing New Tests

### Test Class Structure

```python
class TestNewService:
    """Test class for new service functionality."""

    def test_page_loads(self, ui_server: str, page: Page) -> None:
        """Test that the service page loads correctly."""
        page.goto(f"{ui_server}/new-service")
        assert "New Service" in page.title()

    def test_form_submission(self, ui_server: str, page: Page, sample_data) -> None:
        """Test form submission with valid data."""
        page.goto(f"{ui_server}/new-service")
        # Fill form fields
        page.fill("#field1", sample_data["field1"])
        page.click("button[type='submit']")
        # Verify results
        page.wait_for_selector(".result-panel")
        assert page.locator(".success-message").count() > 0
```

### Best Practices

1. **Use Descriptive Test Names**

   ```python
   def test_csca_certificate_creation_with_valid_data(self):
   ```

2. **Wait for Elements**

   ```python
   page.wait_for_selector(".result-panel", timeout=10000)
   ```

3. **Assert Specific Elements**

   ```python
   assert page.locator(".success-message").count() > 0
   assert "Certificate created" in page.locator(".result-text").inner_text()
   ```

4. **Handle Asynchronous Operations**

   ```python
   page.click("button[type='submit']")
   page.wait_for_load_state("networkidle")
   ```

## Continuous Integration

### GitHub Actions Example

```yaml
name: UI Tests
on: [push, pull_request]

jobs:
  ui-tests:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v6
    - name: Setup Python
      uses: actions/setup-python@v3
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        python tests/ui/setup_tests.py
    - name: Run smoke tests
      run: |
        python tests/ui/test_runner.py smoke
    - name: Run comprehensive tests
      run: |
        python tests/ui/test_runner.py comprehensive
```

## Debugging Tests

### Visual Debugging

1. **Run in Headed Mode**

   ```python
   # In conftest.py
   browser = playwright.chromium.launch(headless=False)
   ```

2. **Add Screenshots**

   ```python
   page.screenshot(path="debug.png")
   ```

3. **Use Playwright Inspector**

   ```bash
   PWDEBUG=1 pytest tests/ui/test_smoke.py::test_specific_test
   ```

### Common Issues

1. **Element Not Found**
   - Increase wait timeouts
   - Check element selectors
   - Wait for page load state

2. **Form Submission Failures**
   - Verify form action URLs
   - Check required field validation
   - Ensure server is running

3. **Navigation Issues**
   - Confirm route definitions
   - Check navigation element selectors
   - Verify server response codes

## Performance Considerations

### Test Optimization

1. **Reuse Browser Sessions**
   - Use session-scoped browser fixture
   - Avoid launching browsers per test

2. **Parallel Execution**
   - Use `pytest-xdist` for parallel runs
   - Be mindful of server port conflicts

3. **Test Data Management**
   - Use fixtures for test data
   - Reset application state between tests

### Monitoring

- Tests should complete in under 5 minutes for full suite
- Individual tests should complete in under 30 seconds
- Smoke tests should complete in under 2 minutes

## Reporting

### HTML Reports

Generated reports include:

- Test execution summary
- Pass/fail status for each test
- Execution times and performance metrics
- Screenshots for failed tests
- Browser console logs

### Integration with VS Code

1. **Test Explorer Integration**
   - Install Python Test Explorer extension
   - Configure pytest as test framework

2. **Debug Configuration**

   ```json
   {
     "name": "Debug UI Tests",
     "type": "python",
     "request": "launch",
     "module": "pytest",
     "args": ["tests/ui/", "-v", "-s"],
     "env": {
       "PWDEBUG": "1"
     }
   }
   ```

## Maintenance

### Regular Tasks

1. **Update Dependencies**

   ```bash
   pip install --upgrade playwright pytest
   playwright install
   ```

2. **Review Test Results**
   - Monitor test execution times
   - Update selectors for UI changes
   - Add tests for new features

3. **Clean Up Test Data**
   - Remove obsolete test fixtures
   - Update sample data as needed
   - Archive old test reports

### Contributing

When adding new UI components:

1. Add smoke tests to `test_smoke.py`
2. Add comprehensive tests to `test_new_ui_e2e.py`
3. Add workflow tests to `test_advanced_workflows.py` if needed
4. Update test runner with new service options
5. Update this documentation

## Troubleshooting

### Common Error Messages

1. **"playwright.sync_api import error"**
   - Run: `pip install playwright`

2. **"Browser not found"**
   - Run: `playwright install chromium`

3. **"Connection refused"**
   - Ensure Marty server is running
   - Check port configuration in conftest.py

4. **"Element not found"**
   - Update element selectors
   - Increase wait timeouts
   - Check page load completion

### Getting Help

- Check Playwright documentation: <https://playwright.dev/python/>
- Review pytest documentation: <https://docs.pytest.org/>
- Open issues in the project repository
- Review existing test implementations for patterns
