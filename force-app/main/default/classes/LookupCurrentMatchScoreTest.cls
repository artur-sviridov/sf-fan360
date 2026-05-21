@isTest
public class LookupCurrentMatchScoreTest {
  private static BroadcastSelectors.LiveMatchSnapshot snap(
    String label,
    Integer goals,
    Datetime ts
  ) {
    BroadcastSelectors.LiveMatchSnapshot s = new BroadcastSelectors.LiveMatchSnapshot();
    s.matchId = 'm1';
    s.fixtureLabel = label;
    s.events = 100;
    s.shots = 12;
    s.goals = goals;
    s.yellowCards = 2;
    s.lastEventAt = ts;
    return s;
  }

  @isTest
  static void returns_isLive_for_recent_snapshot() {
    BroadcastSelectors.overrideLiveMatch = new List<BroadcastSelectors.LiveMatchSnapshot>{
      snap('Arsenal v Chelsea', 2, Datetime.now().addMinutes(-3))
    };
    LookupCurrentMatchScore.Response r = LookupCurrentMatchScore.run(
      new List<LookupCurrentMatchScore.Request>{
        new LookupCurrentMatchScore.Request()
      }
    )[0];
    System.assertEquals(true, r.isLive);
    System.assertEquals(2, r.goals);
    System.assertEquals('Arsenal v Chelsea', r.fixtureLabel);
  }

  @isTest
  static void returns_stale_for_old_snapshot() {
    BroadcastSelectors.overrideLiveMatch = new List<BroadcastSelectors.LiveMatchSnapshot>{
      snap('Old Match', 1, Datetime.now().addHours(-12))
    };
    LookupCurrentMatchScore.Response r = LookupCurrentMatchScore.run(
      new List<LookupCurrentMatchScore.Request>{
        new LookupCurrentMatchScore.Request()
      }
    )[0];
    System.assertEquals(false, r.isLive);
    System.assert(r.note.contains('stale'));
  }

  @isTest
  static void returns_polite_message_when_no_data() {
    BroadcastSelectors.overrideLiveMatch = new List<BroadcastSelectors.LiveMatchSnapshot>();
    LookupCurrentMatchScore.Response r = LookupCurrentMatchScore.run(
      new List<LookupCurrentMatchScore.Request>{
        new LookupCurrentMatchScore.Request()
      }
    )[0];
    System.assertEquals(false, r.isLive);
    System.assert(r.note.contains('No live match'));
  }
}
