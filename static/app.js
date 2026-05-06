const sourceInput = document.getElementById('source_file');
const academicInput = document.getElementById('academic_file');
const uploadForm = document.getElementById('upload_form');
const generateBtn = document.getElementById('generate_btn');
const workflowSteps = document.querySelectorAll('[data-step-target]');
const wizardSections = document.querySelectorAll('.wizard-section');
const nextButtons = document.querySelectorAll('.step-next');
const prevButtons = document.querySelectorAll('.step-prev');

const sourceDropzone = document.querySelector('[data-role="dropzone-source"]');
const academicDropzone = document.querySelector('[data-role="dropzone-academic"]');

const sourceStatus = document.getElementById('status_source');
const academicStatus = document.getElementById('status_academic');
const reviewSource = document.getElementById('review_source');
const reviewAcademic = document.getElementById('review_academic');
const reviewProvider = document.getElementById('review_provider');
const uploadStatus = document.getElementById('upload_status');

const defaultTexts = {
  source: {
    title: 'Drop YouTube script here 📄',
    subtitle: 'Supported: PDF, DOCX, MD, TXT',
  },
  academic: {
    title: 'Optional: drop academic script for sync 📚',
    subtitle: 'Used to generate alignment IDs and parallel sentence references',
  },
};

function setActiveStep(stepNumber) {
  workflowSteps.forEach((button) => {
    const target = Number(button.dataset.stepTarget || 1);
    if (target === stepNumber) {
      button.classList.add('active');
    } else {
      button.classList.remove('active');
    }
  });

  wizardSections.forEach((section) => {
    const sectionStep = Number(section.dataset.step || 1);
    const isCurrent = sectionStep === stepNumber;
    section.classList.toggle('is-hidden', !isCurrent);
    if (isCurrent) {
      section.classList.add('is-active');
    } else {
      section.classList.remove('is-active');
    }
  });
}

function requirePrimaryFile() {
  if (sourceInput?.files?.length) return true;
  sourceInput?.focus();
  if (uploadStatus) {
    uploadStatus.classList.add('status-warning');
    setTimeout(() => uploadStatus.classList.remove('status-warning'), 1200);
  }
  return false;
}

function updateReviewPanel() {
  if (reviewSource) reviewSource.textContent = sourceStatus?.textContent || 'Not selected';
  if (reviewAcademic) reviewAcademic.textContent = academicStatus?.textContent || 'Not selected';
  if (reviewProvider) reviewProvider.textContent = 'xAI Grok (fixed)';
}

function setDropzoneState(dropzone, fileName, defaultText, statusNode) {
  if (!dropzone || !statusNode) return;
  const title = dropzone.querySelector('[data-role="title"]');
  const subtitle = dropzone.querySelector('[data-role="subtitle"]');

  if (fileName) {
    dropzone.classList.add('is-selected');
    if (title) title.textContent = fileName;
    if (subtitle) subtitle.textContent = 'File selected and ready for generation';
    statusNode.textContent = fileName;
  } else {
    dropzone.classList.remove('is-selected');
    if (title) title.textContent = defaultText.title;
    if (subtitle) subtitle.textContent = defaultText.subtitle;
    statusNode.textContent = 'Not selected';
  }
  updateReviewPanel();
}

if (sourceInput) {
  sourceInput.addEventListener('change', () => {
    const fileName = sourceInput.files?.[0]?.name || '';
    setDropzoneState(sourceDropzone, fileName, defaultTexts.source, sourceStatus);
  });
}

if (academicInput) {
  academicInput.addEventListener('change', () => {
    const fileName = academicInput.files?.[0]?.name || '';
    setDropzoneState(academicDropzone, fileName, defaultTexts.academic, academicStatus);
  });
}

workflowSteps.forEach((button) => {
  button.addEventListener('click', () => {
    const targetStep = Number(button.dataset.stepTarget || 1);
    if (targetStep > 1 && !requirePrimaryFile()) return;
    setActiveStep(targetStep);
    if (targetStep === 3) updateReviewPanel();
  });
});

nextButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const nextStep = Number(button.dataset.nextStep || 1);
    if (nextStep > 1 && !requirePrimaryFile()) return;
    setActiveStep(nextStep);
    if (nextStep === 3) updateReviewPanel();
  });
});

prevButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const prevStep = Number(button.dataset.prevStep || 1);
    setActiveStep(prevStep);
  });
});

if (uploadForm) {
  uploadForm.addEventListener('submit', () => {
    setActiveStep(3);
    if (generateBtn) {
      generateBtn.disabled = true;
      generateBtn.textContent = 'Generating package... ⏳';
    }
  });
}

setActiveStep(1);
updateReviewPanel();
