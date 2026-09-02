import '../llm-router-page/index';
import '../i18n/index';
import '../i18n/tr-runtime-lite';
import '../scan-banner/index';
import { initLrAgentmemoryStatus } from '../llm-router-page/agentmemory-status';

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLrAgentmemoryStatus);
} else {
  initLrAgentmemoryStatus();
}
