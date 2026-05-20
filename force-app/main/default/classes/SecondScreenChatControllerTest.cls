@isTest
public class SecondScreenChatControllerTest {

    @isTest
    static void ask_returns_friendly_default_on_blank() {
        SecondScreenChatController.Reply r =
            SecondScreenChatController.ask('Broadcast_Metadata_Agent', '', '');
        System.assert(r.body.contains('Ask me anything'),
            'blank utterance must produce a guide reply');
    }

    @isTest
    static void ask_returns_stub_response_for_real_utterance() {
        SecondScreenChatController.Reply r =
            SecondScreenChatController.ask('Broadcast_Metadata_Agent', 'Salah vs United?', 'Liverpool');
        System.assert(r.body.contains('Salah vs United'),
            'echo path must include the utterance');
    }

    @isTest
    static void latest_snapshot_returns_polite_when_no_data() {
        BroadcastSelectors.overrideLiveMatch = new List<BroadcastSelectors.LiveMatchSnapshot>();
        SecondScreenChatController.Snapshot s = SecondScreenChatController.latestSnapshot();
        System.assertEquals(false, s.isLive);
        System.assertEquals(null, s.fixtureLabel);
    }

    @isTest
    static void latest_snapshot_passes_through_live_data() {
        BroadcastSelectors.LiveMatchSnapshot snap = new BroadcastSelectors.LiveMatchSnapshot();
        snap.matchId = 'm1';
        snap.fixtureLabel = 'Arsenal v Chelsea';
        snap.events = 100;
        snap.shots = 10;
        snap.goals = 2;
        snap.yellowCards = 1;
        snap.lastEventAt = Datetime.now().addMinutes(-2);
        BroadcastSelectors.overrideLiveMatch = new List<BroadcastSelectors.LiveMatchSnapshot>{ snap };

        SecondScreenChatController.Snapshot s = SecondScreenChatController.latestSnapshot();
        System.assertEquals('Arsenal v Chelsea', s.fixtureLabel);
        System.assertEquals(2, s.goals);
        System.assertEquals(true, s.isLive);
        System.assertNotEquals(null, s.lastEventAt);
    }
}
