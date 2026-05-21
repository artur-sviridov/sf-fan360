/**
 * Tests for GetPlayerVsOpponentStats.
 *
 * Strategy: inject test data through BroadcastSelectors.overridePlayerVsOpponent
 * (the @TestVisible escape hatch) so we never need a real Data Cloud CI in a
 * test context. This keeps the tests fast and deterministic.
 */
@isTest
public class GetPlayerVsOpponentStatsTest {
  private static BroadcastSelectors.PlayerOpponentStat row(
    String player,
    String opp,
    Integer goals,
    Decimal xg,
    Integer shots,
    Integer matches,
    String season
  ) {
    BroadcastSelectors.PlayerOpponentStat s = new BroadcastSelectors.PlayerOpponentStat();
    s.playerName = player;
    s.opponentName = opp;
    s.goals = goals;
    s.xgTotal = xg;
    s.shots = shots;
    s.matchesPlayed = matches;
    s.season = season;
    return s;
  }

  @isTest
  static void aggregates_multiple_seasons() {
    BroadcastSelectors.overridePlayerVsOpponent = new List<BroadcastSelectors.PlayerOpponentStat>{
      row('Mohamed Salah', 'Chelsea', 2, 1.8, 12, 4, '2018-19'),
      row('Mohamed Salah', 'Chelsea', 1, 0.7, 6, 2, '2019-20'),
      row('Mohamed Salah', 'Chelsea', 3, 2.1, 9, 4, '2020-21')
    };

    GetPlayerVsOpponentStats.Request req = new GetPlayerVsOpponentStats.Request();
    req.playerName = 'Mohamed Salah';
    req.opponentName = 'Chelsea';

    List<GetPlayerVsOpponentStats.Response> resps = GetPlayerVsOpponentStats.run(
      new List<GetPlayerVsOpponentStats.Request>{ req }
    );

    System.assertEquals(1, resps.size(), 'one response per request');
    GetPlayerVsOpponentStats.Response r = resps[0];
    System.assertEquals(6, r.goals, 'goals must sum across seasons');
    System.assertEquals(27, r.shots, 'shots must sum across seasons');
    System.assertEquals(10, r.matchesPlayed, 'matches must sum');
    System.assert(
      r.citation.contains('PlayerVsOpponent__cio'),
      'citation must reference the CI'
    );
    System.assertEquals(null, r.note, 'no note when data is present');
  }

  @isTest
  static void empty_input_returns_zero_with_note() {
    GetPlayerVsOpponentStats.Request req = new GetPlayerVsOpponentStats.Request();
    req.playerName = '';
    req.opponentName = 'Chelsea';

    List<GetPlayerVsOpponentStats.Response> resps = GetPlayerVsOpponentStats.run(
      new List<GetPlayerVsOpponentStats.Request>{ req }
    );

    System.assertEquals(0, resps[0].goals);
    System.assert(
      resps[0].note != null && resps[0].note.contains('Missing'),
      'must explain missing inputs'
    );
  }

  @isTest
  static void no_rows_returns_zero_with_explanatory_note() {
    BroadcastSelectors.overridePlayerVsOpponent = new List<BroadcastSelectors.PlayerOpponentStat>();

    GetPlayerVsOpponentStats.Request req = new GetPlayerVsOpponentStats.Request();
    req.playerName = 'Unknown Player';
    req.opponentName = 'Chelsea';

    List<GetPlayerVsOpponentStats.Response> resps = GetPlayerVsOpponentStats.run(
      new List<GetPlayerVsOpponentStats.Request>{ req }
    );

    System.assertEquals(0, resps[0].goals);
    System.assert(
      resps[0].note != null && resps[0].note.contains('head-to-head'),
      'must explain coverage limitations'
    );
  }

  @isTest
  static void season_filter_is_passed_through() {
    BroadcastSelectors.overridePlayerVsOpponent = new List<BroadcastSelectors.PlayerOpponentStat>{
      row('Harry Kane', 'Chelsea', 1, 0.6, 4, 1, '2015-16')
    };

    GetPlayerVsOpponentStats.Request req = new GetPlayerVsOpponentStats.Request();
    req.playerName = 'Harry Kane';
    req.opponentName = 'Chelsea';
    req.season = '2015-16';

    List<GetPlayerVsOpponentStats.Response> resps = GetPlayerVsOpponentStats.run(
      new List<GetPlayerVsOpponentStats.Request>{ req }
    );

    System.assertEquals(1, resps[0].goals);
    System.assertEquals(1, resps[0].matchesPlayed);
  }

  @isTest
  static void batch_input_runs_each_independently() {
    BroadcastSelectors.overridePlayerVsOpponent = new List<BroadcastSelectors.PlayerOpponentStat>{
      row('A', 'B', 2, 1.0, 3, 1, '2015-16')
    };

    List<GetPlayerVsOpponentStats.Request> reqs = new List<GetPlayerVsOpponentStats.Request>();
    for (Integer i = 0; i < 5; i++) {
      GetPlayerVsOpponentStats.Request r = new GetPlayerVsOpponentStats.Request();
      r.playerName = 'A';
      r.opponentName = 'B';
      reqs.add(r);
    }

    List<GetPlayerVsOpponentStats.Response> resps = GetPlayerVsOpponentStats.run(
      reqs
    );

    System.assertEquals(5, resps.size());
    for (GetPlayerVsOpponentStats.Response r : resps) {
      System.assertEquals(2, r.goals);
    }
  }
}
