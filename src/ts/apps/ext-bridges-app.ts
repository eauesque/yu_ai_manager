// Lightweight bridges shared by every standalone extension page (/ext/*).
// Currently installs only window.extensionHealthApi so the unified health
// inline scripts in Hailo _*_ui partials can call renderInto() regardless
// of whether the Tools or Extensions page bundle is loaded.
import '../i18n/tr-runtime-lite';
import '../shared/extension-health-bridge';
