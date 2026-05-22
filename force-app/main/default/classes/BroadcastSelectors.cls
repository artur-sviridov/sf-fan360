/**
 * BroadcastSelectors
 * ------------------
 * Lightweight selector layer for the second-screen agent. Follows the
 * fflib Apex Common selector pattern (SOLID dependency-inversion friendly)
 * even though only one consumer exists today - this is the seam we want
 * when Scenario 3 (player scouting) or Scenario 4 (sponsorship hub) reuse
 * the same Data Cloud objects.
 *
 * Each method returns a strongly-typed POJO list, never raw SObject lists,
 * so the agent action classes never touch SObject.
 */
public with sharing class BroadcastSelectors {
  public class PlayerOpponentStat {
    public String playerName;
    public String opponentName;
    public Integer goals;
    public Decimal xgTotal;
    public Integer shots;
    public Integer matchesPlayed;
    public String season;
  }

  public class LiveMatchSnapshot {
    public String matchId;
    public String fixtureLabel;
    public Integer events;
    public Integer shots;
    public Integer goals;
    public Integer yellowCards;
    public Datetime lastEventAt;
  }

  @TestVisible
  private static List<PlayerOpponentStat> overridePlayerVsOpponent;

  @TestVisible
  private static List<LiveMatchSnapshot> overrideLiveMatch;

  /**
   * Look up `player_vs_opponent` Calculated Insight rows.
   *
   * @param playerName    Canonical or raw player name; the CI uses unified id.
   * @param opponentName  Canonical or raw opponent team name.
   * @param season        Optional ISO season label like '2018-19'. Null = all seasons.
   */
  public static List<PlayerOpponentStat> playerVsOpponent(
    String playerName,
    String opponentName,
    String season
  ) {
    if (overridePlayerVsOpponent != null) {
      return overridePlayerVsOpponent;
    }
    // Calculated Insights are queryable via SOQL once Data Cloud
    // surfaces them as `<CI>__cio` standard objects. The dynamic SOQL
    // string is built defensively (whitelisted fields only).
    String soql =
      'SELECT player_name__c, opponent_name__c, goals__c, ' +
      'xg_total__c, shots__c, matches_played__c, season_id__c ' +
      'FROM PlayerVsOpponent__cio ' +
      'WHERE player_name__c = :playerName ' +
      'AND opponent_name__c = :opponentName';
    if (String.isNotBlank(season)) {
      soql += ' AND season_id__c = :season';
    }
    soql += ' WITH SECURITY_ENFORCED ORDER BY season_id__c DESC LIMIT 50';

    List<SObject> records = Database.query(soql);
    List<PlayerOpponentStat> out = new List<PlayerOpponentStat>();
    for (SObject rec : records) {
      PlayerOpponentStat s = new PlayerOpponentStat();
      s.playerName = (String) rec.get('player_name__c');
      s.opponentName = (String) rec.get('opponent_name__c');
      s.goals = (Integer) rec.get('goals__c');
      s.xgTotal = (Decimal) rec.get('xg_total__c');
      s.shots = (Integer) rec.get('shots__c');
      s.matchesPlayed = (Integer) rec.get('matches_played__c');
      s.season = (String) rec.get('season_id__c');
      out.add(s);
    }
    return out;
  }

  public static LiveMatchSnapshot latestLiveMatchSnapshot() {
    if (overrideLiveMatch != null) {
      return overrideLiveMatch.isEmpty() ? null : overrideLiveMatch[0];
    }
    List<SObject> records = Database.query(
      'SELECT match_id__c, fixture_label__c, events__c, shots__c, goals__c, ' +
        'yellow_cards__c, last_event_at__c ' +
        'FROM LiveMatchSnapshot__cio ' +
        'WITH SECURITY_ENFORCED ' +
        'ORDER BY last_event_at__c DESC ' +
        'LIMIT 1'
    );
    if (records.isEmpty()) {
      return null;
    }
    SObject rec = records[0];
    LiveMatchSnapshot snap = new LiveMatchSnapshot();
    snap.matchId = (String) rec.get('match_id__c');
    snap.fixtureLabel = (String) rec.get('fixture_label__c');
    snap.events = (Integer) rec.get('events__c');
    snap.shots = (Integer) rec.get('shots__c');
    snap.goals = (Integer) rec.get('goals__c');
    snap.yellowCards = (Integer) rec.get('yellow_cards__c');
    snap.lastEventAt = (Datetime) rec.get('last_event_at__c');
    return snap;
  }
}
