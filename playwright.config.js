import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir:'tests/browser', timeout:60000, workers:1,
  use:{baseURL:'http://127.0.0.1:8000/quantumcore-wotlk-db/',headless:true,
    launchOptions:process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']} : {}},
  webServer:{command:'python3 -m http.server 8000 --bind 0.0.0.0 --directory ..',url:'http://127.0.0.1:8000/quantumcore-wotlk-db/',reuseExistingServer:!process.env.CI},
});
