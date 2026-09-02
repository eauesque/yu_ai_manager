export type { ApiFailure, ErrorContext, CaughtErrorItem } from './error-reporter-shared';
export { copyText, buildCaughtBundle } from './error-reporter-shared';
export { captureApiFailure, captureThrownError, reportCaughtError, installGlobalErrorReporter } from './error-reporter-events';
export { openErrorReportModal, closeErrorReportModal } from './error-reporter-ui';
