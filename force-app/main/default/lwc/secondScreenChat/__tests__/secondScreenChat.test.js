/**
 * @jest-environment jsdom
 *
 * Smoke tests for the secondScreenChat LWC. They mock the two Apex
 * controllers (`ask` and `latestSnapshot`) plus the lightning/empApi
 * subscription so we can render the component in isolation.
 */

import { createElement } from "lwc";
import SecondScreenChat from "c/secondScreenChat";

jest.mock(
  "@salesforce/apex/SecondScreenChatController.ask",
  () => ({
    default: jest.fn().mockResolvedValue({
      body: "Mocked agent reply",
      citation: "PlayerVsOpponent__cio.goals__c",
      citationUrl: ""
    })
  }),
  { virtual: true }
);

jest.mock(
  "@salesforce/apex/SecondScreenChatController.latestSnapshot",
  () => ({
    default: jest.fn().mockResolvedValue({
      fixtureLabel: "Arsenal v Chelsea",
      goals: 2,
      shots: 10,
      lastEventAt: "14:32",
      isLive: true
    })
  }),
  { virtual: true }
);

jest.mock(
  "lightning/empApi",
  () => ({
    subscribe: jest.fn().mockResolvedValue({}),
    onError: jest.fn()
  }),
  { virtual: true }
);

describe("c-second-screen-chat", () => {
  afterEach(() => {
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
    jest.clearAllMocks();
  });

  function flushPromises() {
    return new Promise((resolve) => setTimeout(resolve, 0));
  }

  it("renders the live score strip from the snapshot", async () => {
    const el = createElement("c-second-screen-chat", { is: SecondScreenChat });
    document.body.appendChild(el);
    await flushPromises();
    const fixture = el.shadowRoot.querySelector(".score-strip .fixture");
    expect(fixture.textContent).toBe("Arsenal v Chelsea");
    const goals = el.shadowRoot.querySelector(".score-strip .goals");
    expect(goals.textContent).toBe("2");
  });

  it("renders the trending prompts", async () => {
    const el = createElement("c-second-screen-chat", { is: SecondScreenChat });
    document.body.appendChild(el);
    await flushPromises();
    const buttons = el.shadowRoot.querySelectorAll(".trending button");
    expect(buttons.length).toBe(5);
  });

  it("sends a question and renders the agent reply", async () => {
    const el = createElement("c-second-screen-chat", { is: SecondScreenChat });
    document.body.appendChild(el);
    await flushPromises();
    const input = el.shadowRoot.querySelector(".composer input");
    input.value = "Salah vs United?";
    input.dispatchEvent(new CustomEvent("change"));
    const form = el.shadowRoot.querySelector(".composer");
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await flushPromises();
    const messages = el.shadowRoot.querySelectorAll(".message");
    expect(messages.length).toBeGreaterThanOrEqual(2);
    const last = messages[messages.length - 1];
    expect(last.classList.contains("agent")).toBe(true);
    expect(last.querySelector(".body").textContent).toBe("Mocked agent reply");
  });
});
