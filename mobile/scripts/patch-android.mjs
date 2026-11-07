// Run after `npx cap add android`: signing config, manifest tweaks.
import fs from 'node:fs';

const gradlePath = 'android/app/build.gradle';
let g = fs.readFileSync(gradlePath, 'utf8');
fs.copyFileSync('signing/pdftoolkit.p12', 'android/app/pdftoolkit.p12');

if (!g.includes('signingConfigs.release')) {
  const signing = `    signingConfigs {
        release {
            storeFile file('pdftoolkit.p12')
            storePassword 'pdftoolkit'
            keyAlias 'pdftoolkit'
            keyPassword 'pdftoolkit'
            storeType 'pkcs12'
        }
    }
`;
  if (!/\n\s*buildTypes\s*\{/.test(g)) throw new Error('buildTypes block not found in build.gradle');
  g = g.replace(/\n(\s*)buildTypes\s*\{/, (m) => '\n' + signing + m.slice(1));
  g = g.replace(/(buildTypes\s*\{\s*release\s*\{)/, '$1\n            signingConfig signingConfigs.release');
  if (!g.includes('signingConfig signingConfigs.release')) throw new Error('release block not patched');
}
g = g.replace(/versionName\s+"[^"]*"/, 'versionName "1.0.0"');
fs.writeFileSync(gradlePath, g);

const manPath = 'android/app/src/main/AndroidManifest.xml';
let m = fs.readFileSync(manPath, 'utf8');
if (!m.includes('windowSoftInputMode')) m = m.replace('<activity', '<activity\n            android:windowSoftInputMode="adjustResize"');
fs.writeFileSync(manPath, m);

// light status bar background matches the app
const stylesPath = 'android/app/src/main/res/values/styles.xml';
if (fs.existsSync(stylesPath)) {
  let s = fs.readFileSync(stylesPath, 'utf8');
  if (!s.includes('android:statusBarColor')) {
    s = s.replace(/(<style name="AppTheme.NoActionBar"[^>]*>)/, '$1\n        <item name="android:statusBarColor">#4f6bed</item>');
    fs.writeFileSync(stylesPath, s);
  }
}
console.log('android project patched');
