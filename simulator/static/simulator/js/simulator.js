/* Progressive enhancement for the simulator.
 *
 * The page already works without this file: every control is a real form, the
 * server runs the commands and redirects. What this adds is the animated
 * version -- the same actions go to the JSON API and the DOM is patched in
 * place, so the robot glides and rotates, and input files play back one
 * command at a time.
 *
 * Deliberately dependency-free and un-built: no npm step for a reviewer to run.
 * Every rule about what a command *does* lives on the server; this file only
 * sends what the user asked for and renders what comes back.
 *
 * Two mechanisms keep it correct:
 *
 *  - A request queue. The session is a signed cookie, so two overlapping
 *    requests would each write a cookie and the later response would silently
 *    discard the earlier one's state. Every call goes through `enqueue`, which
 *    starts a request only after the previous one has finished.
 *
 *  - A generation counter. Any user action (reset, tile click, typed command,
 *    another file) bumps `generation`; a running playback checks it before each
 *    step and stops when it has been superseded.
 */
(function () {
  "use strict";

  const app = document.getElementById("app");
  if (!app) return;

  const el = {
    commandForm: document.getElementById("command-form"),
    script: document.getElementById("script"),
    board: document.getElementById("board"),
    robot: document.getElementById("robot"),
    readout: document.getElementById("readout"),
    log: document.getElementById("log"),
    status: document.getElementById("status"),
    placeForm: document.getElementById("place-form"),
    fileForm: document.getElementById("file-form"),
    program: document.getElementById("program"),
    programTitle: document.getElementById("program-title"),
    programLines: document.getElementById("program-lines"),
    programStop: document.getElementById("program-stop"),
  };

  const urls = {
    command: app.dataset.commandUrl,
    place: app.dataset.placeUrl,
    reset: app.dataset.resetUrl,
    fileStart: (name) => app.dataset.fileStartUrl.replace("__name__", encodeURIComponent(name)),
  };

  const stepDelay = Number(app.dataset.stepDelay) || 650;
  let generation = 0;
  let playing = false;
  let queue = Promise.resolve();

  /* --- plumbing ---------------------------------------------------------- */

  function csrfToken() {
    const field = document.querySelector("[name=csrfmiddlewaretoken]");
    return field ? field.value : "";
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    }).then((response) => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  /* Run `task` after every earlier request has settled; resolve with its result. */
  function enqueue(task) {
    const run = queue.then(task, task);
    queue = run.catch(() => {});
    return run;
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function setStatus(text, isError) {
    el.status.textContent = text;
    el.status.style.color = isError ? "var(--danger)" : "";
  }

  function fail(err) {
    setStatus("LINK FAILURE", true);
    console.error(err);
  }

  /* --- rendering --------------------------------------------------------- */

  function renderRobot(data) {
    const robot = el.robot;
    if (!data.robot) {
      robot.classList.add("robot--hidden");
      robot.setAttribute("aria-label", "Robot not placed");
      return;
    }
    robot.classList.remove("robot--hidden");
    robot.style.setProperty("--x", data.robot.x);
    robot.style.setProperty("--y", data.robot.y);
    robot.dataset.facing = data.robot.facing;
    robot.setAttribute(
      "aria-label",
      `Robot at ${data.robot.x},${data.robot.y} facing ${data.robot.facing}`
    );
  }

  function renderCells(data) {
    el.board.querySelectorAll(".cell").forEach((cell) => {
      const occupied =
        !!data.robot &&
        Number(cell.dataset.x) === data.robot.x &&
        Number(cell.dataset.y) === data.robot.y;
      cell.classList.toggle("cell--occupied", occupied);
    });
  }

  function renderReadout(data) {
    el.readout.textContent = data.report
      ? "> OUTPUT: " + data.report
      : "> AWAITING PLACE COMMAND";
  }

  function logItem(className, source, message) {
    const li = document.createElement("li");
    li.className = className;
    if (source !== null) {
      const cmd = document.createElement("span");
      cmd.className = "log-cmd";
      cmd.textContent = source;
      li.appendChild(cmd);
    }
    const msg = document.createElement("span");
    msg.className = "log-msg";
    // textContent, not innerHTML: server messages echo user input back.
    msg.textContent = message;
    li.appendChild(msg);
    return li;
  }

  function renderLog(entries) {
    el.log.replaceChildren();
    if (!entries.length) {
      el.log.appendChild(
        logItem(
          "log-entry log-entry--muted",
          null,
          "Board clear. Click any tile to place the robot, or run an input file."
        )
      );
      return;
    }
    entries.forEach((entry) => {
      const kind = entry.error ? " log-entry--error" : entry.accepted ? "" : " log-entry--ignored";
      el.log.appendChild(logItem("log-entry" + kind, entry.source, entry.message));
    });
    el.log.scrollTop = el.log.scrollHeight;
  }

  function flashBlocked() {
    el.robot.classList.remove("robot--blocked");
    void el.robot.offsetWidth; // restart the animation on consecutive refusals
    el.robot.classList.add("robot--blocked");
  }

  /* Render a response. `data.added` is how many log entries the request made. */
  function render(data) {
    renderRobot(data);
    renderCells(data);
    renderReadout(data);
    const log = data.log || [];
    renderLog(log);
    const added = data.added ? log.slice(-data.added) : [];
    const refused = added.some((entry) => !entry.accepted);
    if (refused && data.robot) flashBlocked();
    setStatus(refused ? "COMMAND IGNORED" : "READY", refused);
    return added;
  }

  /* --- program listing (input-file playback) ----------------------------- */

  function showProgram(file) {
    el.programTitle.textContent = "RUNNING: " + file.title;
    el.programLines.replaceChildren(
      ...file.lines.map((line) => {
        const li = document.createElement("li");
        li.textContent = line;
        return li;
      })
    );
    el.program.hidden = false;
    el.programStop.hidden = false;
    markActiveFile(file.name);
  }

  function markLine(index, className) {
    const li = el.programLines.children[index];
    if (!li) return;
    li.className = className;
    if (className === "line--current") keepInView(el.programLines, li);
  }

  /* Scroll `list` (only) so `item` is visible. scrollIntoView would also
     scroll the page, yanking controls out from under the user's cursor. */
  function keepInView(list, item) {
    const top = item.offsetTop;
    const bottom = top + item.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }

  function markActiveFile(name) {
    el.fileForm.querySelectorAll(".file").forEach((item) => {
      item.classList.toggle("file--active", item.dataset.file === name);
    });
  }

  function endProgram(label) {
    el.programTitle.textContent = label;
    el.programStop.hidden = true;
    markActiveFile(null);
  }

  /* --- actions ----------------------------------------------------------- */

  /* Cancel any running playback. Returns the new generation for the caller. */
  function supersede() {
    generation += 1;
    if (playing) {
      playing = false;
      endProgram("PROGRAM STOPPED");
    }
    return generation;
  }

  function stop() {
    if (!playing) return;
    supersede();
    setStatus("STOPPED");
  }

  function sendCommand(script) {
    if (!script.trim()) return;
    supersede();
    setStatus("RUNNING...");
    enqueue(() => post(urls.command, { script }))
      .then(render)
      .catch(fail);
  }

  function placeAt(x, y) {
    supersede();
    const checked = el.placeForm.querySelector("input[name=facing]:checked");
    const facing = checked ? checked.value : "NORTH";
    enqueue(() => post(urls.place, { x, y, facing }))
      .then(render)
      .catch(fail);
  }

  function reset() {
    supersede();
    el.program.hidden = true;
    enqueue(() => post(urls.reset))
      .then((data) => {
        render(data);
        setStatus("BOARD CLEAR — CLICK A TILE TO PLACE");
        el.script.value = "";
      })
      .catch(fail);
  }

  /* Reset the board, then send the file's lines one at a time. */
  async function playFile(name) {
    const mine = supersede();
    setStatus("LOADING " + name.toUpperCase() + "...");
    try {
      const start = await enqueue(() => post(urls.fileStart(name)));
      if (mine !== generation) return;
      render(start);
      showProgram(start.file);
      playing = true;

      const lines = start.file.lines;
      for (let i = 0; i < lines.length; i++) {
        if (mine !== generation) return;
        markLine(i, "line--current");
        setStatus(`STEP ${i + 1}/${lines.length}: ${lines[i]}`);
        const data = await enqueue(() => post(urls.command, { script: lines[i] }));
        if (mine !== generation) return;
        const [entry] = render(data);
        markLine(
          i,
          entry && entry.error ? "line--error" : entry && !entry.accepted ? "line--ignored" : "line--done"
        );
        if (i < lines.length - 1) await sleep(stepDelay);
      }
      if (mine === generation) {
        playing = false;
        endProgram("FINISHED: " + start.file.title);
        setStatus("RUN COMPLETE");
      }
    } catch (err) {
      if (mine === generation) {
        playing = false;
        endProgram("PROGRAM STOPPED");
        fail(err);
      }
    }
  }

  /* --- wiring ------------------------------------------------------------ */

  el.commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    // The RESET button submits this same form; honour it without a reload.
    if (event.submitter && event.submitter.value === "reset") reset();
    else sendCommand(el.script.value);
  });

  el.script.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      sendCommand(el.script.value);
    }
  });

  // Tiles are submit buttons for #place-form; intercept to place without a reload.
  el.placeForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const tile = event.submitter;
    if (tile && tile.dataset.x !== undefined) {
      placeAt(Number(tile.dataset.x), Number(tile.dataset.y));
    }
  });

  el.fileForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (event.submitter && event.submitter.value) playFile(event.submitter.value);
  });

  el.programStop.addEventListener("click", stop);

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      sendCommand(button.dataset.command);
    });
  });

  const KEY_COMMANDS = {
    ArrowUp: "MOVE",
    ArrowLeft: "LEFT",
    ArrowRight: "RIGHT",
    Enter: "REPORT",
  };

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      stop();
      return;
    }
    const active = document.activeElement;
    const tag = active && active.tagName;
    // Leave typing to the text box, and Enter on a focused button (a tile, a
    // file) to that button. Arrows still drive the robot after a tile click.
    if (tag === "TEXTAREA" || tag === "INPUT") return;
    if (tag === "BUTTON" && event.key === "Enter") return;
    const command = KEY_COMMANDS[event.key];
    if (!command) return;
    event.preventDefault();
    sendCommand(command);
  });

  setStatus("READY");
  if (app.dataset.autoplay) playFile(app.dataset.autoplay);
})();
