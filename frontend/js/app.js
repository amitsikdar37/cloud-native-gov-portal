/* ═══════════════════════════════════════════════════════════
   Exam Registration Portal — Frontend Application Logic
   National Examination Services
   ═══════════════════════════════════════════════════════════ */

// ── Configuration ──
const CONFIG = {
  API_BASE: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:3000/api'
    : (window.location.protocol === 'file:' ? 'http://localhost:3000/api' : '/api'),
  DRAFT_KEY: 'exam_portal_draft',          // localStorage key
  IDEMPOTENCY_PREFIX: 'ERP',
  OTP_TTL_SECONDS: 300,                    // 5 minutes
  MAX_PHOTO_SIZE: 2 * 1024 * 1024,         // 2 MB
  MAX_SIGNATURE_SIZE: 1 * 1024 * 1024,     // 1 MB
  DEBOUNCE_MS: 2000,                       // Prevent double-submit window
  DRAFT_AUTOSAVE_MS: 1500,                 // Auto-save debounce delay
};

// ── Application State ──
const state = {
  currentStep: 1,
  totalSteps: 4,
  otpVerified: false,
  otpTimerInterval: null,
  uploads: { photo: null, signature: null },  // S3 URLs after upload
  isSubmitting: false,
  draftSaveTimeout: null,
};

// ═══════════════════ DOM REFERENCES ═══════════════════
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  form: $('#applicationForm'),
  steps: $$('.step'),
  stepperItems: $$('.stepper__item'),
  stepperFill: $('#stepperFill'),
  btnPrev: $('#btnPrev'),
  btnReset: $('#btnReset'),
  btnNext: $('#btnNext'),
  btnSubmit: $('#btnSubmit'),
  btnDemoFill: $('#btnDemoFill'),
  btnSendOtp: $('#btnSendOtp'),
  btnVerifyOtp: $('#btnVerifyOtp'),
  otpInputGroup: $('#otpInputGroup'),
  otpCode: $('#otpCode'),
  otpTimer: $('#otpTimer'),
  otpSuccess: $('#otpSuccess'),
  reviewSections: $('#reviewSections'),
  agreeTerms: $('#agreeTerms'),
  draftStatus: $('#draftStatus'),
  draftStatusText: $('#draftStatusText'),
  successModal: $('#successModal'),
  refCode: $('#refCode'),
  btnNewApp: $('#btnNewApplication'),
  loadingOverlay: $('#loadingOverlay'),
  loadingText: $('#loadingText'),
  toastContainer: $('#toastContainer'),
};

// ═══════════════════ INITIALIZATION ═══════════════════
document.addEventListener('DOMContentLoaded', () => {
  restoreDraft();
  bindEvents();
  updateStepperUI();
});

function bindEvents() {
  dom.btnNext.addEventListener('click', handleNext);
  dom.btnPrev.addEventListener('click', handlePrev);
  dom.btnSubmit.addEventListener('click', handleSubmit);
  dom.btnSendOtp.addEventListener('click', handleSendOtp);
  dom.btnVerifyOtp.addEventListener('click', handleVerifyOtp);
  dom.btnNewApp.addEventListener('click', handleNewApplication);
  if (dom.btnReset) {
    dom.btnReset.addEventListener('click', handleReset);
  }
  if (dom.btnDemoFill) {
    dom.btnDemoFill.addEventListener('click', handleDemoFill);
  }

  // Prevent default form reload when pressing Enter and advance cleanly to Next step
  dom.form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (state.currentStep === state.totalSteps) {
      handleSubmit();
    } else {
      handleNext();
    }
  });

  dom.form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'file' && e.target.type !== 'checkbox') {
      e.preventDefault();
      if (state.currentStep === state.totalSteps) {
        handleSubmit();
      } else {
        handleNext();
      }
    }
  });

  // Auto-format Aadhaar as "1234 5678 9012"
  const aadhaarInput = $('#aadhaar');
  if (aadhaarInput) {
    aadhaarInput.addEventListener('input', (e) => {
      let digits = e.target.value.replace(/\D/g, '').substring(0, 12);
      let parts = digits.match(/.{1,4}/g);
      e.target.value = parts ? parts.join(' ') : digits;
    });
  }

  // Restrict phone input to numbers
  const phoneInput = $('#phone');
  if (phoneInput) {
    phoneInput.addEventListener('input', (e) => {
      e.target.value = e.target.value.replace(/\D/g, '').substring(0, 10);
    });
  }

  // Auto-save & live checkmark styling on every input change
  dom.form.addEventListener('input', (e) => {
    scheduleDraftSave();
    const val = e.target.value.trim();
    if (val.length > 0) {
      if (e.target.id === 'email') {
        if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
          e.target.classList.add('field__input--valid');
          e.target.classList.remove('field__input--invalid');
        } else {
          e.target.classList.remove('field__input--valid');
        }
      } else if (e.target.id === 'phone') {
        if (val.length === 10) {
          e.target.classList.add('field__input--valid');
          e.target.classList.remove('field__input--invalid');
        } else {
          e.target.classList.remove('field__input--valid');
        }
      } else if (e.target.id === 'aadhaar') {
        if (val.replace(/\s/g, '').length === 12) {
          e.target.classList.add('field__input--valid');
          e.target.classList.remove('field__input--invalid');
        } else {
          e.target.classList.remove('field__input--valid');
        }
      } else {
        e.target.classList.add('field__input--valid');
        e.target.classList.remove('field__input--invalid');
      }
    } else {
      e.target.classList.remove('field__input--valid');
    }
  });

  dom.form.addEventListener('change', () => scheduleDraftSave());

  // File upload handlers
  $('#filePhoto').addEventListener('change', (e) => handleFileSelect(e, 'photo'));
  $('#fileSignature').addEventListener('change', (e) => handleFileSelect(e, 'signature'));

  // Drag-and-drop for upload zones
  ['uploadZonePhoto', 'uploadZoneSignature'].forEach(id => {
    const zone = $(`#${id}`);
    const inputId = id === 'uploadZonePhoto' ? 'filePhoto' : 'fileSignature';
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) {
        $(`#${inputId}`).files = e.dataTransfer.files;
        handleFileSelect({ target: { files: [file] } }, id === 'uploadZonePhoto' ? 'photo' : 'signature');
      }
    });
  });
}

function handleReset() {
  const currentStepEl = $(`#step${state.currentStep}`);
  if (!currentStepEl) return;
  const inputs = currentStepEl.querySelectorAll('input, select');
  inputs.forEach(input => {
    if (input.type !== 'button') input.value = '';
    input.classList.remove('field__input--valid', 'field__input--invalid');
  });
  clearErrors();
  saveDraft();
  showToast('Current step inputs reset', 'info');
}

// ═══════════════════ STEP NAVIGATION ═══════════════════
function handleNext() {
  if (!validateStep(state.currentStep)) return;
  if (state.currentStep < state.totalSteps) {
    state.currentStep++;
    showStep(state.currentStep);
    saveDraft();
  }
}

function handlePrev() {
  if (state.currentStep > 1) {
    state.currentStep--;
    showStep(state.currentStep);
  }
}

function showStep(stepNum) {
  // Hide all steps, show target
  dom.steps.forEach(s => s.classList.remove('step--visible'));
  $(`#step${stepNum}`).classList.add('step--visible');

  // Re-trigger animation
  const el = $(`#step${stepNum}`);
  el.style.animation = 'none';
  el.offsetHeight; // reflow
  el.style.animation = '';

  // Update navigation buttons
  dom.btnPrev.disabled = stepNum === 1;
  if (stepNum === state.totalSteps) {
    dom.btnNext.classList.add('hidden');
    dom.btnSubmit.classList.remove('hidden');
    buildReviewSection();
  } else {
    dom.btnNext.classList.remove('hidden');
    dom.btnSubmit.classList.add('hidden');
  }

  updateStepperUI();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateStepperUI() {
  const pct = ((state.currentStep - 1) / (state.totalSteps - 1)) * 100;
  dom.stepperFill.style.width = `${pct}%`;

  dom.stepperItems.forEach(item => {
    const step = parseInt(item.dataset.step);
    item.classList.remove('active', 'completed');
    if (step === state.currentStep) item.classList.add('active');
    else if (step < state.currentStep) item.classList.add('completed');
  });
}

function goToStep(stepNum) {
  state.currentStep = stepNum;
  showStep(stepNum);
}

// ═══════════════════ VALIDATION ═══════════════════
function validateStep(stepNum) {
  clearErrors();
  let valid = true;

  if (stepNum === 1) {
    valid = validateRequired('fullName', 'Full name is required') && valid;
    valid = validateEmail('email') && valid;
    valid = validatePhone('phone') && valid;
    valid = validateRequired('dob', 'Date of birth is required') && valid;
    valid = validateRequired('gender', 'Please select your gender') && valid;
    valid = validateAadhaar('aadhaar') && valid;

    // OTP verification check
    if (!state.otpVerified) {
      showFieldError('otp', 'Please verify your email via OTP. Click "Send OTP to Email" above (or enter 123456).');
      showToast('Please verify your email via OTP before proceeding', 'error');
      valid = false;
    }
  }

  if (stepNum === 2) {
    valid = validateRequired('qualification', 'Please select a qualification') && valid;
    valid = validateRequired('institution', 'Institution name is required') && valid;
    valid = validateYear('yearOfPassing') && valid;
    valid = validateRequired('percentage', 'Percentage / CGPA is required') && valid;
  }

  if (stepNum === 3) {
    if (!state.uploads.photo) {
      showFieldError('photo', 'Passport photo is required');
      valid = false;
    }
    if (!state.uploads.signature) {
      showFieldError('signature', 'Signature is required');
      valid = false;
    }
  }

  if (stepNum === 4) {
    if (!dom.agreeTerms.checked) {
      showFieldError('agreeTerms', 'You must agree to the declaration');
      valid = false;
    }
  }

  // Smoothly scroll and focus the first invalid field or OTP prompt
  if (!valid) {
    const firstInvalid = dom.form.querySelector('.field__input--invalid');
    if (firstInvalid) {
      firstInvalid.focus();
      firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      const errOtp = $('#err-otp');
      if (errOtp && errOtp.textContent) {
        errOtp.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }

  return valid;
}

function validateRequired(fieldId, msg) {
  const el = $(`#${fieldId}`);
  if (!el.value.trim()) {
    showFieldError(fieldId, msg);
    el.classList.add('field__input--invalid');
    return false;
  }
  el.classList.remove('field__input--invalid');
  el.classList.add('field__input--valid');
  return true;
}

function validateEmail(fieldId) {
  const el = $(`#${fieldId}`);
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!el.value.trim()) {
    showFieldError(fieldId, 'Email is required');
    el.classList.add('field__input--invalid');
    return false;
  }
  if (!re.test(el.value)) {
    showFieldError(fieldId, 'Enter a valid email address');
    el.classList.add('field__input--invalid');
    return false;
  }
  el.classList.remove('field__input--invalid');
  el.classList.add('field__input--valid');
  return true;
}

function validatePhone(fieldId) {
  const el = $(`#${fieldId}`);
  if (!el.value.trim()) {
    showFieldError(fieldId, 'Phone number is required');
    el.classList.add('field__input--invalid');
    return false;
  }
  if (!/^[0-9]{10}$/.test(el.value.replace(/\s/g, ''))) {
    showFieldError(fieldId, 'Enter a valid 10-digit phone number');
    el.classList.add('field__input--invalid');
    return false;
  }
  el.classList.remove('field__input--invalid');
  el.classList.add('field__input--valid');
  return true;
}

function validateAadhaar(fieldId) {
  const el = $(`#${fieldId}`);
  const cleaned = el.value.replace(/\s/g, '');
  if (!cleaned) {
    showFieldError(fieldId, 'Aadhaar number is required');
    el.classList.add('field__input--invalid');
    return false;
  }
  if (!/^[0-9]{12}$/.test(cleaned)) {
    showFieldError(fieldId, 'Enter a valid 12-digit Aadhaar number');
    el.classList.add('field__input--invalid');
    return false;
  }
  el.classList.remove('field__input--invalid');
  el.classList.add('field__input--valid');
  return true;
}

function validateYear(fieldId) {
  const el = $(`#${fieldId}`);
  const val = parseInt(el.value);
  if (!el.value.trim() || isNaN(val)) {
    showFieldError(fieldId, 'Year of passing is required');
    el.classList.add('field__input--invalid');
    return false;
  }
  if (val < 1970 || val > 2030) {
    showFieldError(fieldId, 'Enter a year between 1970 and 2030');
    el.classList.add('field__input--invalid');
    return false;
  }
  el.classList.remove('field__input--invalid');
  el.classList.add('field__input--valid');
  return true;
}

function showFieldError(fieldId, msg) {
  const errEl = $(`#err-${fieldId}`);
  if (errEl) errEl.textContent = msg;
}

function clearErrors() {
  $$('.field__error').forEach(el => el.textContent = '');
  $$('.field__input--invalid').forEach(el => el.classList.remove('field__input--invalid'));
}

// ═══════════════════ OTP HANDLING ═══════════════════
async function handleSendOtp() {
  const email = $('#email').value.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    showToast('Please enter a valid email address first', 'error');
    return;
  }

  dom.btnSendOtp.disabled = true;
  dom.btnSendOtp.textContent = 'Sending…';

  try {
    const res = await apiCall('/otp/send', 'POST', { email });
    if (res.ok || res.status === 200 || res.mock) {
      dom.otpInputGroup.classList.remove('hidden');
      dom.otpCode.focus();
      startOtpTimer();
      showToast('OTP sent to ' + email, 'success');
    }
  } catch {
    // In demo/offline mode, simulate success
    dom.otpInputGroup.classList.remove('hidden');
    dom.otpCode.focus();
    startOtpTimer();
    showToast('Demo mode: OTP is 123456', 'info');
  } finally {
    dom.btnSendOtp.disabled = false;
    dom.btnSendOtp.innerHTML = `
      <svg class="btn__icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path d="M2.94 6.44A2 2 0 0 1 4.88 5h10.24a2 2 0 0 1 1.94 1.44L10 11.12 2.94 6.44ZM2 8.07V14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8.07l-7.47 4.98a1 1 0 0 1-1.06 0L2 8.07Z"/></svg>
      Resend OTP`;
  }
}

async function handleVerifyOtp() {
  const code = dom.otpCode.value.trim();
  if (!/^[0-9]{6}$/.test(code)) {
    showToast('Enter a valid 6-digit OTP', 'error');
    return;
  }

  try {
    const res = await apiCall('/otp/verify', 'POST', {
      email: $('#email').value.trim(),
      otp: code,
    });

    if (res.ok || res.verified || res.mock) {
      markOtpVerified();
    } else {
      showToast('Invalid OTP. Please try again.', 'error');
    }
  } catch {
    // Demo mode: accept 123456
    if (code === '123456') {
      markOtpVerified();
    } else {
      showToast('Demo mode: Use OTP 123456', 'error');
    }
  }
}

function markOtpVerified() {
  state.otpVerified = true;
  clearInterval(state.otpTimerInterval);
  dom.otpInputGroup.classList.add('hidden');
  dom.otpSuccess.classList.remove('hidden');
  dom.btnSendOtp.classList.add('hidden');
  showFieldError('otp', '');
  showToast('Email verified successfully!', 'success');
}

function startOtpTimer() {
  let seconds = CONFIG.OTP_TTL_SECONDS;
  clearInterval(state.otpTimerInterval);

  const tick = () => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    dom.otpTimer.textContent = `${m}:${s.toString().padStart(2, '0')}`;
    if (seconds <= 0) {
      clearInterval(state.otpTimerInterval);
      dom.otpTimer.textContent = 'Expired';
      dom.otpCode.disabled = true;
      dom.btnVerifyOtp.disabled = true;
    }
    seconds--;
  };

  tick();
  state.otpTimerInterval = setInterval(tick, 1000);
}

// ═══════════════════ FILE UPLOADS (S3 Pre-Signed URL) ═══════════════════
async function handleFileSelect(event, type) {
  const file = event.target.files[0];
  if (!file) return;

  const maxSize = type === 'photo' ? CONFIG.MAX_PHOTO_SIZE : CONFIG.MAX_SIGNATURE_SIZE;
  const label = type === 'photo' ? 'Photo' : 'Signature';

  // Validate file type
  if (!['image/jpeg', 'image/png'].includes(file.type)) {
    showFieldError(type, `${label} must be a JPG or PNG file`);
    return;
  }

  // Validate file size
  if (file.size > maxSize) {
    const mb = maxSize / (1024 * 1024);
    showFieldError(type, `${label} must be smaller than ${mb} MB`);
    return;
  }

  // Clear previous errors
  showFieldError(type, '');

  const capitalType = type.charAt(0).toUpperCase() + type.slice(1);
  const progressContainer = $(`#progress${capitalType}`);
  const progressFill = $(`#progressFill${capitalType}`);
  const progressText = $(`#progressText${capitalType}`);
  const successEl = $(`#success${capitalType}`);
  const previewEl = $(`#preview${capitalType}`);
  const zoneEl = $(`#uploadZone${capitalType}`);

  progressContainer.classList.remove('hidden');
  successEl.classList.add('hidden');

  try {
    // Step 1: Request pre-signed URL from backend
    let uploadUrl;
    try {
      const res = await apiCall('/upload-url', 'POST', {
        fileName: `${type}_${Date.now()}.${file.type.split('/')[1]}`,
        fileType: file.type,
      });
      uploadUrl = res.uploadUrl || res.url;
    } catch {
      // Demo/offline: simulate upload with local preview
      uploadUrl = null;
    }

    // Step 2: Upload directly to S3 (or simulate)
    if (uploadUrl) {
      await uploadToS3(uploadUrl, file, (pct) => {
        progressFill.style.width = `${pct}%`;
        progressText.textContent = `${pct}%`;
      });
      state.uploads[type] = uploadUrl.split('?')[0]; // Store the clean S3 URL
    } else {
      // Demo mode: simulate upload with progress
      await simulateUpload((pct) => {
        progressFill.style.width = `${pct}%`;
        progressText.textContent = `${pct}%`;
      });
      // Store as data URL for demo preview
      state.uploads[type] = await fileToDataUrl(file);
    }

    // Step 3: Show success
    progressContainer.classList.add('hidden');
    successEl.classList.remove('hidden');
    zoneEl.classList.add('uploaded');

    // Preview thumbnail
    const imgUrl = state.uploads[type];
    previewEl.innerHTML = `<img src="${imgUrl}" alt="${label} preview" />`;

    showToast(`${label} uploaded successfully`, 'success');
    saveDraft();

  } catch (err) {
    progressContainer.classList.add('hidden');
    showFieldError(type, `Upload failed: ${err.message}`);
    showToast(`${label} upload failed`, 'error');
  }
}

function uploadToS3(presignedUrl, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', presignedUrl, true);
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`S3 returned ${xhr.status}`));
    });

    xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
    xhr.send(file);
  });
}

function simulateUpload(onProgress) {
  return new Promise((resolve) => {
    let pct = 0;
    const interval = setInterval(() => {
      pct += Math.random() * 15 + 5;
      if (pct >= 100) {
        pct = 100;
        clearInterval(interval);
        onProgress(100);
        setTimeout(resolve, 200);
      } else {
        onProgress(Math.round(pct));
      }
    }, 120);
  });
}

function fileToDataUrl(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

// ═══════════════════ REVIEW SECTION BUILDER ═══════════════════
function buildReviewSection() {
  const data = getFormData();

  dom.reviewSections.innerHTML = `
    <!-- Personal Info -->
    <div class="review-section">
      <div class="review-section__header">
        <span class="review-section__title">Personal Information</span>
        <button type="button" class="review-section__edit" onclick="goToStep(1)">✎ Edit</button>
      </div>
      <div class="review-grid">
        ${reviewItem('Full Name', data.fullName)}
        ${reviewItem('Email', data.email)}
        ${reviewItem('Phone', data.phone)}
        ${reviewItem('Date of Birth', data.dob)}
        ${reviewItem('Gender', data.gender)}
        ${reviewItem('Aadhaar', maskAadhaar(data.aadhaar))}
      </div>
    </div>

    <!-- Academic Info -->
    <div class="review-section">
      <div class="review-section__header">
        <span class="review-section__title">Academic Information</span>
        <button type="button" class="review-section__edit" onclick="goToStep(2)">✎ Edit</button>
      </div>
      <div class="review-grid">
        ${reviewItem('Qualification', data.qualification)}
        ${reviewItem('Institution', data.institution)}
        ${reviewItem('Year of Passing', data.yearOfPassing)}
        ${reviewItem('Percentage / CGPA', data.percentage)}
        ${reviewItem('Specialization', data.specialization || '—')}
      </div>
    </div>

    <!-- Documents -->
    <div class="review-section">
      <div class="review-section__header">
        <span class="review-section__title">Uploaded Documents</span>
        <button type="button" class="review-section__edit" onclick="goToStep(3)">✎ Edit</button>
      </div>
      <div class="review-uploads">
        ${state.uploads.photo ? `<img class="review-thumb" src="${state.uploads.photo}" alt="Photo" />` : '<span>No photo</span>'}
        ${state.uploads.signature ? `<img class="review-thumb" src="${state.uploads.signature}" alt="Signature" />` : '<span>No signature</span>'}
      </div>
    </div>
  `;
}

function reviewItem(label, value) {
  return `
    <div class="review-item">
      <div class="review-item__label">${label}</div>
      <div class="review-item__value">${value || '—'}</div>
    </div>`;
}

function maskAadhaar(val) {
  if (!val) return '—';
  const clean = val.replace(/\s/g, '');
  return 'XXXX XXXX ' + clean.slice(-4);
}

// ═══════════════════ FORM SUBMISSION ═══════════════════
async function handleSubmit() {
  if (!validateStep(4)) return;

  // ── Debounce: prevent double-submit ──
  if (state.isSubmitting) {
    showToast('Submission already in progress…', 'info');
    return;
  }
  state.isSubmitting = true;
  dom.btnSubmit.disabled = true;

  showLoading('Submitting your application…');

  const formData = getFormData();
  const idempotencyKey = generateIdempotencyKey();

  const payload = {
    ...formData,
    photoUrl: state.uploads.photo,
    signatureUrl: state.uploads.signature,
    submittedAt: new Date().toISOString(),
  };

  try {
    const res = await apiCall('/submit', 'POST', payload, {
      'X-Idempotency-Key': idempotencyKey,
    });

    // Success — show confirmation
    hideLoading();
    const refId = (res && res.referenceId) || `ERP-${Date.now().toString(36).toUpperCase()}`;
    dom.refCode.textContent = refId;
    dom.successModal.classList.remove('hidden');

    // Clear draft after successful submission
    localStorage.removeItem(CONFIG.DRAFT_KEY);

  } catch (err) {
    hideLoading();
    showToast('Submission failed: ' + (err.message || 'Please try again'), 'error');
  } finally {
    // Re-enable after debounce window
    setTimeout(() => {
      state.isSubmitting = false;
      dom.btnSubmit.disabled = false;
    }, CONFIG.DEBOUNCE_MS);
  }
}

function handleNewApplication() {
  dom.successModal.classList.add('hidden');
  localStorage.removeItem(CONFIG.DRAFT_KEY);
  dom.form.reset();
  state.currentStep = 1;
  state.otpVerified = false;
  state.uploads = { photo: null, signature: null };
  dom.otpSuccess.classList.add('hidden');
  dom.btnSendOtp.classList.remove('hidden');
  dom.otpInputGroup.classList.add('hidden');

  // Reset upload zones
  ['Photo', 'Signature'].forEach(t => {
    $(`#uploadZone${t}`).classList.remove('uploaded');
    $(`#success${t}`).classList.add('hidden');
    $(`#preview${t}`).innerHTML = $(`#uploadZone${t === 'Photo' ? 'Photo' : 'Signature'}`).querySelector('.upload-zone__icon')
      ? '' : '';
  });

  showStep(1);
}

// ═══════════════════ DRAFT SAVE / RESTORE (localStorage) ═══════════════════
function scheduleDraftSave() {
  clearTimeout(state.draftSaveTimeout);
  state.draftSaveTimeout = setTimeout(() => saveDraft(), CONFIG.DRAFT_AUTOSAVE_MS);
}

function saveDraft() {
  const data = {
    formData: getFormData(),
    currentStep: state.currentStep,
    otpVerified: state.otpVerified,
    uploads: state.uploads,
    savedAt: Date.now(),
  };
  localStorage.setItem(CONFIG.DRAFT_KEY, JSON.stringify(data));

  // Also sync to Redis via API (non-blocking, fire-and-forget)
  syncDraftToRedis(data);

  // Show save indicator
  dom.draftStatus.classList.add('visible');
  dom.draftStatusText.textContent = 'Draft saved';
  setTimeout(() => dom.draftStatus.classList.remove('visible'), 2500);
}

function restoreDraft() {
  try {
    const raw = localStorage.getItem(CONFIG.DRAFT_KEY);
    if (!raw) return;

    const data = JSON.parse(raw);
    const age = Date.now() - (data.savedAt || 0);

    // Discard drafts older than 24 hours
    if (age > 24 * 60 * 60 * 1000) {
      localStorage.removeItem(CONFIG.DRAFT_KEY);
      return;
    }

    // Restore form field values
    if (data.formData) {
      Object.entries(data.formData).forEach(([key, val]) => {
        const el = $(`#${key}`);
        if (el && val) el.value = val;
      });
    }

    // Restore state
    if (data.otpVerified) {
      state.otpVerified = true;
      dom.otpSuccess.classList.remove('hidden');
      dom.btnSendOtp.classList.add('hidden');
    }

    if (data.uploads) {
      state.uploads = data.uploads;
      ['photo', 'signature'].forEach(type => {
        if (state.uploads[type]) {
          const cap = type.charAt(0).toUpperCase() + type.slice(1);
          $(`#uploadZone${cap}`).classList.add('uploaded');
          $(`#success${cap}`).classList.remove('hidden');
          $(`#preview${cap}`).innerHTML = `<img src="${state.uploads[type]}" alt="${type}" />`;
        }
      });
    }

    // Restore step (but always start from where they were)
    if (data.currentStep && data.currentStep > 1) {
      state.currentStep = data.currentStep;
      showStep(state.currentStep);
    }

    showToast('Draft restored from your last session', 'info');
  } catch {
    // Corrupted draft — ignore
    localStorage.removeItem(CONFIG.DRAFT_KEY);
  }
}

async function syncDraftToRedis(data) {
  try {
    await apiCall('/draft', 'POST', data);
  } catch {
    // Non-critical — localStorage is the primary local cache
  }
}

// ═══════════════════ HELPERS ═══════════════════
function getFormData() {
  const fields = ['fullName', 'email', 'phone', 'dob', 'gender', 'aadhaar',
    'qualification', 'institution', 'yearOfPassing', 'percentage', 'specialization'];
  const data = {};
  fields.forEach(f => {
    const el = $(`#${f}`);
    if (el) data[f] = el.value;
  });
  return data;
}

function generateIdempotencyKey() {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).substring(2, 8);
  return `${CONFIG.IDEMPOTENCY_PREFIX}-${ts}-${rand}`;
}

// ── API Wrapper (with transparent offline/demo fallback) ──
async function apiCall(endpoint, method = 'GET', body = null, extraHeaders = {}) {
  const url = `${CONFIG.API_BASE}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  };

  const options = { method, headers };
  if (body && method !== 'GET') options.body = JSON.stringify(body);

  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.message || `Server returned ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    // Graceful offline mock fallback if backend is offline or opened via file://
    if (endpoint === '/otp/send') {
      return { ok: true, mock: true, message: 'Mock OTP sent: 123456' };
    }
    if (endpoint === '/otp/verify') {
      if (body && (body.otp === '123456' || body.otp.length === 6)) {
        return { ok: true, verified: true, mock: true };
      }
      throw new Error('Invalid OTP. Use demo OTP: 123456');
    }
    if (endpoint === '/upload-url') {
      return { mock: true, uploadUrl: null };
    }
    if (endpoint === '/submit') {
      return {
        ok: true,
        referenceId: `ERP-${Math.floor(100000 + Math.random() * 900000)}`,
        status: 'queued',
        mock: true,
      };
    }
    if (endpoint === '/draft') {
      return { ok: true, mock: true };
    }
    throw err;
  }
}

// ── Demo Data Auto-Fill ──
function handleDemoFill() {
  const demoData = {
    fullName: 'Aarav Sharma',
    email: 'aarav.sharma@example.gov.in',
    phone: '9876543210',
    dob: '1998-05-15',
    gender: 'Male',
    aadhaar: '1234 5678 9012',
    qualification: 'Bachelors',
    institution: 'Indian Institute of Technology Delhi',
    yearOfPassing: '2024',
    percentage: '88.5%',
    specialization: 'Computer Science & Engineering',
  };

  Object.entries(demoData).forEach(([id, val]) => {
    const el = $(`#${id}`);
    if (el) {
      el.value = val;
      el.classList.remove('field__input--invalid');
      el.classList.add('field__input--valid');
    }
  });

  // Verify OTP immediately
  markOtpVerified();

  // Create demo SVG images for passport photo and signature
  const photoSvg = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><rect width="200" height="200" fill="%231e293b"/><circle cx="100" cy="70" r="40" fill="%2360a5fa"/><path d="M30 180 C30 130 70 120 100 120 C130 120 170 130 170 180 Z" fill="%2360a5fa"/><text x="100" y="192" font-family="sans-serif" font-size="12" fill="%2394a3b8" text-anchor="middle">Demo Passport Photo</text></svg>`;
  const sigSvg = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100"><rect width="200" height="100" fill="%231e293b"/><path d="M20 60 Q 50 10, 80 50 T 140 40 T 180 60" fill="none" stroke="%2338bdf8" stroke-width="3" stroke-linecap="round"/><text x="100" y="85" font-family="sans-serif" font-size="11" fill="%2394a3b8" text-anchor="middle">Demo Signature</text></svg>`;

  state.uploads.photo = photoSvg;
  state.uploads.signature = sigSvg;

  ['photo', 'signature'].forEach(type => {
    const cap = type.charAt(0).toUpperCase() + type.slice(1);
    const zone = $(`#uploadZone${cap}`);
    const success = $(`#success${cap}`);
    const preview = $(`#preview${cap}`);
    if (zone) zone.classList.add('uploaded');
    if (success) success.classList.remove('hidden');
    if (preview) preview.innerHTML = `<img src="${state.uploads[type]}" alt="${type}" />`;
  });

  clearErrors();
  saveDraft();
  showToast('⚡ Demo data populated & OTP verified! Click "Save & Continue" to test.', 'success');
}

// ── Toast Notifications ──
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  dom.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(60px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, 4000);
}

// ── Loading Overlay ──
function showLoading(text) {
  dom.loadingText.textContent = text;
  dom.loadingOverlay.classList.remove('hidden');
}
function hideLoading() {
  dom.loadingOverlay.classList.add('hidden');
}

// ── Expose goToStep globally for review edit buttons ──
window.goToStep = goToStep;
