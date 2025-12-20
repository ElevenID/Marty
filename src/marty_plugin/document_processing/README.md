# Document Processing API

A FastAPI-based document processing service focusing on MRZ (Machine Readable Zone) document processing. This implementation provides a comprehensive API for document verification and data extraction with support for various document formats.

## 🚀 Features

- **MRZ Processing**: Full support for TD-1, TD-2, and TD-3 MRZ formats
- **Generic Document API**: Flexible document processing interface
- **Multiple Input Formats**: Support for base64 encoded images and image URLs
- **Health Monitoring**: Comprehensive health check endpoints
- **Authentication**: Optional API key authentication
- **Docker Support**: Ready-to-deploy containerized solution
- **Comprehensive Testing**: Unit tests and end-to-end test suite

## 📋 API Endpoints

### Health Endpoints

- `GET /api/ping` - Simple liveness check
- `GET /api/health` - Detailed health information
- `GET /api/healthz` - Kubernetes-style health check
- `GET /api/readyz` - License validation check

### Processing Endpoints

- `POST /api/process` - Main document processing endpoint

### Documentation

- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

## 🛠️ Installation & Setup

### Local Development

1. **Clone the repository**:

```bash
git clone <repository-url>
cd Marty/src/regula_clone
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Configure environment** (optional):

```bash
cp .env.example .env
# Edit .env file with your configuration
```

4. **Run the server**:

```bash
python -m uvicorn app.main:app --host localhost --port 8080 --reload
```

5. **Access the API**:
   - API: <http://localhost:8080>
   - Documentation: <http://localhost:8080/docs>
   - Health Check: <http://localhost:8080/api/health>

### Docker Deployment

1. **Build and run with Docker Compose**:

```bash
docker-compose up --build
```

2. **Access the containerized API**:
   - API: <http://localhost:8080>
   - Health Check: <http://localhost:8080/api/ping>

3. **Run tests in container**:

```bash
docker-compose --profile test up doc-processing-test
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `development` |
| `DEBUG` | Enable debug mode | `true` |
| `HOST` | Server host address | `localhost` |
| `PORT` | Server port | `8080` |
| `USE_API_KEY` | Enable API key authentication | `false` |
| `API_KEY` | API key for authentication | `` |
| `LICENSE_ID` | Mock license identifier | `4d43a2af-e321-496c-9a4e-5a8f3d26df0e` |
| `CORE_VERSION` | Core library version | `1.2.3` |

## 📝 Usage Examples

### Basic MRZ Processing

```python
import requests
import base64

# Prepare the request
with open("passport_image.jpg", "rb") as f:
    image_data = base64.b64encode(f.read()).decode('utf-8')

payload = {
    "processParam": {
        "scenario": "Mrz",
        "resultTypeOutput": ["MrzText", "MrzFields"]
    },
    "List": [
        {
            "ImageData": image_data
        }
    ],
    "tag": "my-session"
}

headers = {
    "Content-Type": "application/json",
    "X-API-Key": "your-api-key"  # Optional if API key auth is enabled
}

# Send request
response = requests.post(
    "http://localhost:8080/api/process",
    json=payload,
    headers=headers
)

# Process response
if response.status_code == 200:
    result = response.json()
    transaction_info = result["transactionInfo"]
    containers = result["containerList"]["List"]

    for container in containers:
        if container["type"] == "MrzContainer" and container["mrzResult"]:
            mrz = container["mrzResult"]
            print(f"Document Type: {mrz['docType']}")
            print(f"Document Number: {mrz['documentNumber']}")
            print(f"Name: {mrz['givenNames']} {mrz['surname']}")
            print(f"Nationality: {mrz['nationality']}")
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');
const fs = require('fs');

async function processMRZ(imagePath) {
    // Read and encode image
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');

    const payload = {
        processParam: {
            scenario: "Mrz",
            strictImageQuality: true,
            imageQa: {
                minFocus: 40,
                maxGlare: 30
            }
        },
        List: [{
            ImageData: base64Image
        }],
        tag: "js-client-session"
    };

    try {
        const response = await axios.post(
            'http://localhost:8080/api/process',
            payload,
            {
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': 'your-api-key'
                }
            }
        );

        const result = response.data;
        console.log('Processing completed in:', result.elapsedTime, 'ms');
        console.log('Transaction ID:', result.transactionInfo.requestId);

        return result;
    } catch (error) {
        console.error('Processing failed:', error.response?.data || error.message);
        throw error;
    }
}
```

### Health Check Example

```bash
# Simple ping
curl http://localhost:8080/api/ping

# Detailed health info
curl http://localhost:8080/api/health

# Kubernetes-style health check
curl http://localhost:8080/api/healthz
```

## 🧪 Testing

### Unit Tests

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run with coverage
python -m pytest tests/unit/ --cov=app --cov-report=html
```

### End-to-End Tests

```bash
# Start the server first
python -m uvicorn app.main:app --host localhost --port 8080 &

# Run E2E tests
python -m pytest tests/e2e/ -v

# Or run the standalone E2E test
python tests/e2e/test_e2e_workflow.py
```

### Test Coverage

The test suite covers:

- ✅ All API endpoints (health and processing)
- ✅ MRZ processing logic
- ✅ Image handling and validation
- ✅ Error scenarios and edge cases
- ✅ Authentication mechanisms
- ✅ Concurrent request handling
- ✅ Large image processing
- ✅ Multiple image batch processing

## 🏗️ Architecture

```
src/document_processing/
├── app/
│   ├── api/
│   │   ├── deps.py          # Dependency injection
│   │   └── endpoints.py     # API route handlers
│   ├── core/
│   │   └── config.py        # Configuration management
│   ├── models/
│   │   └── document_models.py # Pydantic data models
│   ├── services/
│   │   └── mrz_service.py   # MRZ processing logic
│   └── main.py              # FastAPI application
├── tests/
│   ├── unit/                # Unit tests
│   └── e2e/                 # End-to-end tests
├── Dockerfile               # Container definition
├── docker-compose.yml      # Multi-container setup
└── requirements.txt         # Python dependencies
```

## 🔄 Integration with Marty

This Document Processing API is designed to integrate with the larger Marty document verification ecosystem:

- **MRZ Utilities**: Uses `src/marty_common/utils/mrz_utils.py` for MRZ parsing
- **Data Models**: Compatible with `src/marty_common/models/passport.py`
- **Shared Libraries**: Leverages common crypto and validation utilities

## 🐛 Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running from the correct directory and all dependencies are installed
2. **Port Conflicts**: Change the port in configuration if 8080 is already in use
3. **Image Processing Failures**: Check image format and base64 encoding
4. **API Key Issues**: Verify API key configuration and headers

### Debug Mode

Enable debug mode for detailed logging:

```bash
export DEBUG=true
export ENVIRONMENT=development
python -m uvicorn app.main:app --reload --log-level debug
```

### Health Monitoring

Monitor the service health:

```bash
# Check if service is responding
curl -f http://localhost:8080/api/ping || echo "Service is down"

# Get detailed health metrics
curl http://localhost:8080/api/health | jq '.'
```

## 🚀 Deployment

### Production Deployment

1. **Environment Configuration**:

```bash
export ENVIRONMENT=production
export DEBUG=false
export USE_API_KEY=true
export API_KEY=your-secure-api-key
```

2. **Docker Production**:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

3. **Load Balancing**: Use nginx or similar for load balancing multiple instances

4. **Monitoring**: Implement health check monitoring and logging

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: doc-processing
spec:
  replicas: 3
  selector:
    matchLabels:
      app: doc-processing
  template:
    metadata:
      labels:
        app: doc-processing
    spec:
      containers:
      - name: doc-processing
        image: doc-processing:latest
        ports:
        - containerPort: 8080
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: USE_API_KEY
          value: "true"
        livenessProbe:
          httpGet:
            path: /api/ping
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /api/readyz
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
```

## 📄 License

This project is part of the Marty ecosystem and follows the same licensing terms. See the main project license for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📞 Support

For issues and questions:

- Check the troubleshooting section
- Review the test cases for usage examples
- Open an issue in the main Marty repository

---

**Note**: This is a generic document processing implementation designed for testing and development. For production use with real documents, ensure proper validation and security measures are in place.
