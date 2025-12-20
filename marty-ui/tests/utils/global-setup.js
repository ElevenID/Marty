// Global setup for Playwright tests
const axios = require('axios');

async function globalSetup() {
  console.log('🚀 Starting E2E test setup...');

  // Wait for demo application to be ready
  const maxRetries = 30;
  const retryDelay = 2000; // 2 seconds

  for (let i = 0; i < maxRetries; i++) {
    try {
      console.log(`⏳ Checking if demo is ready (attempt ${i + 1}/${maxRetries})...`);

      // Check main UI
  const base = process.env.BASE_URL || 'http://localhost:9080';
  await axios.get(base, { timeout: 5000 });

      // Check backend services
      const services = [
        { name: 'Issuer', url: `${base.replace(/\/$/, '')}/api/issuer/health` },
        { name: 'Verifier', url: `${base.replace(/\/$/, '')}/api/verifier/health` },
        { name: 'Wallet', url: `${base.replace(/\/$/, '')}/api/wallet/health` }
      ];

      for (const service of services) {
        try {
          await axios.get(service.url, { timeout: 3000 });
          console.log(`✅ ${service.name} service is ready`);
        } catch (error) {
          console.log(`⚠️  ${service.name} service not ready yet`);
        }
      }

      console.log('✅ Demo application is ready!');
      return;
    } catch (error) {
      if (i === maxRetries - 1) {
        throw new Error(
          `❌ Demo application failed to start after ${maxRetries} attempts. ` +
          'Please ensure the demo is running with ./deploy-k8s.sh'
        );
      }
      console.log(`⏳ Demo not ready yet, retrying in ${retryDelay}ms...`);
      await new Promise(resolve => setTimeout(resolve, retryDelay));
    }
  }
}

module.exports = globalSetup;
