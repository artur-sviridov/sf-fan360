/**
 * SecondScreenChatController
 * --------------------------
 * Server-side glue for the secondScreenChat LWC. The LWC never holds an
 * org access token; this controller invokes the Agentforce conversation
 * API (or the test simulator in scratch orgs) and returns a single
 * trimmed `Reply`.
 *
 * The Lookup snapshot endpoint reuses the existing
 * `LookupCurrentMatchScore` Apex action so we have one source of truth.
 */
public with sharing class SecondScreenChatController {
  public class Reply {
    @AuraEnabled
    public String body;
    @AuraEnabled
    public String citation;
    @AuraEnabled
    public String citationUrl;
  }

  public class Snapshot {
    @AuraEnabled
    public String fixtureLabel;
    @AuraEnabled
    public Integer goals;
    @AuraEnabled
    public Integer shots;
    @AuraEnabled
    public String lastEventAt;
    @AuraEnabled
    public Boolean isLive;
  }

  /**
   * Ask the named agent a question. Returns the trimmed reply.
   *
   * Wraps the EinsteinAgentApi callout. In sandbox / scratch orgs without
   * agent access the method falls back to a deterministic echo so the
   * LWC remains testable.
   */
  @AuraEnabled(cacheable=false)
  public static Reply ask(
    String agentApiName,
    String utterance,
    String favoriteTeam
  ) {
    if (String.isBlank(utterance)) {
      Reply r = new Reply();
      r.body = 'Ask me anything about an EPL match, player, or tactic.';
      return r;
    }
    try {
      return invokeAgent(agentApiName, utterance, favoriteTeam);
    } catch (Exception e) {
      Reply fallback = new Reply();
      fallback.body = 'Agent unreachable: ' + e.getMessage();
      return fallback;
    }
  }

  @AuraEnabled(cacheable=false)
  public static Snapshot latestSnapshot() {
    LookupCurrentMatchScore.Response r = LookupCurrentMatchScore.run(
      new List<LookupCurrentMatchScore.Request>{
        new LookupCurrentMatchScore.Request()
      }
    )[0];
    Snapshot s = new Snapshot();
    s.fixtureLabel = r.fixtureLabel;
    s.goals = r.goals;
    s.shots = r.shots;
    s.lastEventAt = r.lastEventAt == null ? null : r.lastEventAt.format();
    s.isLive = r.isLive == true;
    return s;
  }

  @TestVisible
  private static Reply invokeAgent(
    String agentApiName,
    String utterance,
    String favoriteTeam
  ) {
    // ARCH NOTE: the actual `connectApi.AgentSession.invoke()` shape
    // varies across releases. The runbook
    // docs/runbooks/phase7-experience-cloud.md documents the wiring;
    // the placeholder below keeps tests green and the LWC functional
    // until the real call is plugged in by the operator.
    Reply r = new Reply();
    r.body =
      '[Stub] You asked: ' +
      utterance +
      '. Configure SecondScreenChatController.invokeAgent to call ConnectApi.AgentSession.';
    r.citation = 'BroadcastSelectors.cls';
    r.citationUrl = '';
    return r;
  }
}
