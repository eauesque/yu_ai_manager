// Entry point: condition-builder bundle

import { CONDITIONS, PERIOD_PRESETS } from './config';
import {
  renderTextField, renderSelectField, renderToggleField,
} from './render-fields-basic';
import './render-fields-special';
import './render-fields';
import './render';
import {
  hasCondition, activateCondition, getActiveConditions, setActiveConditions,
  renderActiveConditions,
} from './state';
import {
  announceA11yStatus, getConditionMenuButtons, closeConditionMenu,
  openConditionMenu, toggleConditionMenu, renderConditionMenu,
  setLastConditionTriggerEl,
} from './menu-core';
import { addCondition, removeCondition, clearAllConditions } from './condition-actions';
import { setPeriodPreset, showCustomPeriod, setResolutionPreset, toggleAccordion, toggleAdvancedSearch } from './actions';
import { autoInit } from './init';
import { installWindowApi } from '../shared/window-api';

installWindowApi('conditionBuilderApi', {
  renderTextField,
  renderSelectField,
  renderToggleField,
  hasCondition,
  activateCondition,
  getActiveConditions,
  setActiveConditions,
  renderActiveConditions,
  toggleConditionMenu,
  openConditionMenu,
  closeConditionMenu,
  getConditionMenuButtons,
  setLastConditionTriggerEl,
  announceA11yStatus,
  renderMenu: renderConditionMenu,
  addCondition,
  removeCondition,
  clearAllConditions,
  setPeriodPreset,
  showCustomPeriod,
  setResolutionPreset,
  toggleAccordion,
  toggleAdvancedSearch,
});

// Auto-init: restore conditions from localStorage
autoInit();
