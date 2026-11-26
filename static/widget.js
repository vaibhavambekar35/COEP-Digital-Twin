(() => {
  const script = document.currentScript;
  const chatUrl = script?.dataset.chatUrl || new URL("/", script.src).origin;
  const panelId = "document-chat-widget-panel";
  if (document.getElementById("document-chat-widget-button")) return;

  const style = document.createElement("style");
  style.textContent = `
    #document-chat-widget-button {
      position: fixed; right: 24px; bottom: 24px; z-index: 2147483000;
      width: 58px; height: 58px; display: grid; place-items: center;
      border: 0; border-radius: 18px; color: #18251e; background: #d7ec75;
      box-shadow: 0 8px 26px #18251e35; cursor: pointer;
      transition: transform 160ms ease, background 160ms ease;
    }
    #document-chat-widget-button:hover { transform: translateY(-2px); background: #cce363; }
    #document-chat-widget-button svg { width: 24px; height: 24px; }
    #${panelId} {
      position: fixed; right: 24px; bottom: 96px; z-index: 2147482999;
      width: min(390px, calc(100vw - 32px)); height: min(620px, calc(100dvh - 128px));
      overflow: hidden; border: 1px solid #dce4d9; border-radius: 15px; background: #fffefa;
      box-shadow: 0 18px 55px #18251e30;
    }
    #${panelId}[hidden] { display: none; }
    #${panelId} iframe { width: 100%; height: 100%; border: 0; }
    @media (max-width: 480px) {
      #${panelId} { right: 8px; bottom: 78px; width: calc(100vw - 16px); height: calc(100dvh - 96px); }
      #document-chat-widget-button { right: 16px; bottom: 16px; }
    }
  `;
  document.head.append(style);

  const panel = document.createElement("div");
  panel.id = panelId;
  panel.hidden = true;
  const frame = document.createElement("iframe");
  frame.title = "Document Chat";
  frame.src = `${chatUrl.replace(/\/$/, "")}/?embed=1`;
  panel.append(frame);

  const button = document.createElement("button");
  button.id = "document-chat-widget-button";
  button.type = "button";
  button.setAttribute("aria-label", "Open document chat");
  button.setAttribute("aria-expanded", "false");
  button.title = "Open document chat";
  button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 5.75h14v10.5H10l-5 3v-13.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8.5 9.5h7m-7 3h4.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  button.addEventListener("click", () => {
    const opening = panel.hidden;
    panel.hidden = !opening;
    button.setAttribute("aria-expanded", String(opening));
    button.setAttribute("aria-label", opening ? "Close document chat" : "Open document chat");
    button.title = opening ? "Close document chat" : "Open document chat";
  });

  document.body.append(panel, button);
})();