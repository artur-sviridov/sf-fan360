/**
 * LookupCurrentMatchScore
 * -----------------------
 * Invocable Apex used by the LiveMatchTopic. Returns the most-recent
 * snapshot from `LiveMatchSnapshot__cio`.
 *
 * If there is no active match (CI empty or last_event older than 4 hours),
 * the agent surfaces a polite "no live match right now" with a hint to ask
 * a historical question instead.
 */
public with sharing class LookupCurrentMatchScore {
  public class Request {
  }

  public class Response {
    @InvocableVariable
    public String fixtureLabel;
    @InvocableVariable
    public Integer events;
    @InvocableVariable
    public Integer shots;
    @InvocableVariable
    public Integer goals;
    @InvocableVariable
    public Datetime lastEventAt;
    @InvocableVariable
    public Boolean isLive;
    @InvocableVariable
    public String citation;
    @InvocableVariable
    public String note;
  }

  @InvocableMethod(
    label='Lookup Current Match Score'
    description='Returns the most recent LiveMatchSnapshot__cio aggregation.'
    category='Broadcast Metadata Agent'
  )
  public static List<Response> run(List<Request> requests) {
    List<Response> out = new List<Response>();
    for (Integer i = 0; i < (requests == null ? 1 : requests.size()); i++) {
      out.add(snapshot());
    }
    return out;
  }

  @TestVisible
  private static Response snapshot() {
    Response r = new Response();
    r.citation = 'Calculated Insight LiveMatchSnapshot__cio';
    BroadcastSelectors.LiveMatchSnapshot s = BroadcastSelectors.latestLiveMatchSnapshot();
    if (s == null) {
      r.isLive = false;
      r.note = 'No live match data available right now. Ask a historical question instead.';
      return r;
    }
    r.fixtureLabel = s.fixtureLabel;
    r.events = s.events;
    r.shots = s.shots;
    r.goals = s.goals;
    r.lastEventAt = s.lastEventAt;
    if (s.lastEventAt != null && s.lastEventAt < Datetime.now().addHours(-4)) {
      r.isLive = false;
      r.note =
        'Snapshot is stale (last event ' +
        s.lastEventAt.format() +
        '). No live match in progress.';
    } else {
      r.isLive = true;
    }
    return r;
  }
}
