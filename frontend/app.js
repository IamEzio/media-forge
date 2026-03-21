const form = document.getElementById("job-form");
const statusBox = document.getElementById("status");
const jobIdEl = document.getElementById("job-id");
const jobStatusEl = document.getElementById("job-status");
const jobErrorEl = document.getElementById("job-error");
const downloadBtn = document.getElementById("download-btn");

let currentJobId = null;
let currentJobType = null;
let pollTimer = null;

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const videoFile = document.getElementById("video").files[0];
  const subtitlesFile = document.getElementById("subtitles").files[0];
  const jobType = document.getElementById("job_type").value;

  if (!videoFile) {
    alert("Please select a video file.");
    return;
  }

  const formData = new FormData();
  formData.append("video", videoFile);
  if (subtitlesFile) {
    formData.append("subtitles", subtitlesFile);
  }
  formData.append("job_type", jobType);

  form.querySelector("button[type=submit]").disabled = true;
  jobErrorEl.textContent = "";

  try {
    const res = await fetch("/jobs", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Request failed with ${res.status}`);
    }

    const data = await res.json();
    currentJobId = data.job_id;
    currentJobType = jobType;

    statusBox.classList.remove("hidden");
    jobIdEl.textContent = currentJobId;
    jobStatusEl.textContent = data.status;
    downloadBtn.classList.add("hidden");

    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 3000);
  } catch (err) {
    console.error(err);
    alert("Failed to submit job: " + err.message);
  } finally {
    form.querySelector("button[type=submit]").disabled = false;
  }
});

async function pollStatus() {
  if (!currentJobId) return;

  try {
    const res = await fetch(`/jobs/${currentJobId}`);
    if (!res.ok) {
      throw new Error(`Status request failed: ${res.status}`);
    }
    const data = await res.json();
    jobStatusEl.textContent = data.status;
    jobErrorEl.textContent = data.error || "";

    if (data.status === "completed") {
      clearInterval(pollTimer);
      downloadBtn.classList.remove("hidden");
      downloadBtn.onclick = () => {
        window.location.href = `/jobs/${currentJobId}/download?job_type=${encodeURIComponent(
          currentJobType
        )}`;
      };
    }
  } catch (err) {
    console.error(err);
  }
}
