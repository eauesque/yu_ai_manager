import { attach } from '../shared/prompt-linter/prompt-linter';

(window as unknown as Record<string, unknown>)['PromptLinter'] = { attach };
