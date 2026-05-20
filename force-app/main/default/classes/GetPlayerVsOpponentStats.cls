/**
 * GetPlayerVsOpponentStats
 * ------------------------
 * Invocable Apex action exposed to Agentforce.
 *
 * Powers the reference query: "Has anyone scored more goals against
 * Chelsea than Salah?" The agent calls this action, gets a
 * structured response, and produces a citation referencing the
 * `PlayerVsOpponent__cio` Calculated Insight.
 *
 * Inputs:
 *   playerName     required - canonical or raw player name
 *   opponentName   required - canonical or raw opponent team name
 *   season         optional - ISO season label like '2018-19'
 *
 * Output:
 *   goals, assists (placeholder=null until source has it), xg, matches,
 *   citation        - DMO field name path for the reasoning trace.
 */
public with sharing class GetPlayerVsOpponentStats {

    public class Request {
        @InvocableVariable(required=true description='Canonical or raw player name. E.g. "Mohamed Salah".')
        public String playerName;
        @InvocableVariable(required=true description='Canonical or raw opponent team name. E.g. "Chelsea".')
        public String opponentName;
        @InvocableVariable(description='Optional ISO season label like "2018-19". Omit for all seasons.')
        public String season;
    }

    public class Response {
        @InvocableVariable
        public String playerName;
        @InvocableVariable
        public String opponentName;
        @InvocableVariable
        public Integer goals;
        @InvocableVariable
        public Decimal xgTotal;
        @InvocableVariable
        public Integer shots;
        @InvocableVariable
        public Integer matchesPlayed;
        @InvocableVariable
        public String citation;
        @InvocableVariable
        public String note;
    }

    @InvocableMethod(
        label='Get Player Vs Opponent Stats'
        description='Aggregated goals/xG/shots for a player against an opponent across all available seasons.'
        category='Broadcast Metadata Agent'
    )
    public static List<Response> run(List<Request> requests) {
        List<Response> out = new List<Response>();
        for (Request r : requests) {
            out.add(handle(r));
        }
        return out;
    }

    @TestVisible
    private static Response handle(Request r) {
        Response resp = new Response();
        resp.playerName = r.playerName;
        resp.opponentName = r.opponentName;
        resp.citation = 'Calculated Insight PlayerVsOpponent__cio fields: '
            + 'goals__c, xg_total__c, shots__c, matches_played__c';

        if (String.isBlank(r.playerName) || String.isBlank(r.opponentName)) {
            resp.goals = 0;
            resp.note = 'Missing player or opponent. Required inputs: playerName, opponentName.';
            return resp;
        }

        List<BroadcastSelectors.PlayerOpponentStat> stats = BroadcastSelectors.playerVsOpponent(
            r.playerName, r.opponentName, r.season
        );

        Integer totalGoals = 0;
        Decimal totalXg = 0;
        Integer totalShots = 0;
        Integer totalMatches = 0;
        for (BroadcastSelectors.PlayerOpponentStat s : stats) {
            if (s.goals != null) { totalGoals += s.goals; }
            if (s.xgTotal != null) { totalXg += s.xgTotal; }
            if (s.shots != null) { totalShots += s.shots; }
            if (s.matchesPlayed != null) { totalMatches += s.matchesPlayed; }
        }
        resp.goals = totalGoals;
        resp.xgTotal = totalXg;
        resp.shots = totalShots;
        resp.matchesPlayed = totalMatches;

        if (stats.isEmpty()) {
            resp.note = 'No rows in PlayerVsOpponent__cio for ' + r.playerName
                + ' vs ' + r.opponentName + '. This build does not load per-player '
                + 'event attribution; use head-to-head or match marts for team history.';
        }
        return resp;
    }
}
