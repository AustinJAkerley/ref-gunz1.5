#pragma once
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

struct sqlite3;
class MMatchServer;
class MMatchStage;
class MMatchObject;

namespace competitive { namespace economy {
// GBucks is the existing Character.BP wallet, NOT converted experience.
// Only committed rewards enter the live wallet; NEVER pass them to IncBP.
struct Player {
    int cid = 0, aid = 0, team = 0;
    bool bot = false, spectator = false, inBattle = false;
};
struct Kill {
    Player attacker, victim;
    bool playing = false, allowedMode = false, sameStage = false;
    bool victimAlive = false, teamGame = false, activeDuelPair = true;
};
bool eligible(const Kill& kill);
// Rounded expected reward against this opponent, inclusive 10..20; equal=15.
int killReward(int attackerElo, int victimElo);
// One SELECT snapshot of server-owned DuelRating; missing rows default to 1000.
// SQL failures throw, never silently fall back to a default reward.
int killReward(sqlite3* db, int attackerCID, int victimCID);

enum class Kind : int { Begin = 1, Join, Leave, Kill, Finish, Close };
struct Event {
    std::string id, match;
    Kind kind = Kind::Begin;
    // New kills use amount=0: Elo is read inside the FIRST successful record
    // transaction, not at death time. Credited stores that immutable award.
    // Amount remains the original payload for collision/replay validation.
    int cid = 0, aid = 0, victim = 0, victimAid = 0, amount = 0;
};
bool operator==(const Event& a, const Event& b);

// One instance per entire stage launch, never per Duel round. Membership is
// keyed by persistent CID: reconnecting cannot erase the leave tombstone.
class Match {
    struct Member { int aid = 0; bool left = false; };
    std::string id_;
    std::uint64_t sequence_ = 0;
    bool closed_ = true;
    std::map<int, Member> members_;
    Event event(Kind kind, int cid = 0, int aid = 0);
public:
    const std::string& id() const { return id_; }
    std::vector<Event> begin(const std::string& id);
    std::vector<Event> join(const Player& player);
    std::vector<Event> leave(const Player& player);
    std::vector<Event> kill(const Kill& kill);
    std::vector<Event> finish(const std::vector<Player>& remaining);
    std::vector<Event> abort();
};

struct Result { bool applied = false, replay = false; int credited = 0; };
struct RewardNotification {
    int cid = 0, amount = 0;
    bool completion = false;
    std::uint64_t session = 0;
};
// Volatile, best-effort notices, NOT another money ledger. A nonzero session
// identifies the online connection at credit time. Never populate from login
// wallet deltas or historical ledger rows. record's replay result suppresses
// duplicates even after take() removes the pending EventID.
class RewardNotifications {
    std::map<std::string, RewardNotification> pending_;
public:
    void committed(const Event& event, const Result& result, std::uint64_t session);
    // Discard disconnected/replaced sessions; consume ready notices BEFORE
    // sending so an exception/ambiguous send cannot cause a retry popup.
    std::vector<RewardNotification> take(const std::map<int, std::uint64_t>& online,
                                        const std::set<int>& walletsReady);
};
// All helpers throw on SQL failure; transactions roll back completely.
// initialize does not alter BP, XP or Level. Existing store.cpp owns Level99.
void initialize(sqlite3* db);
Result record(sqlite3* db, const Event& event);
std::int64_t rewardTotal(sqlite3* db, int cid);
std::int64_t earned(sqlite3* db, const std::string& match, int cid);
void initializeJournal(sqlite3* db);
void enqueue(sqlite3* db, const Event& event);
bool oldest(sqlite3* db, Event& event);
void acknowledge(sqlite3* db, const std::string& id);

// loadedTotal MUST come from the SAME SQLite SELECT snapshot as loaded BP.
// Synchronize by monotonic reward total, not by replacing BP from the DB:
// this preserves unrelated pending cache debits and synchronous shop spending.
bool syncWallet(int& bp, long long& loadedTotal, std::int64_t committedTotal);
} }

// Adapter implemented only with GUNZ_ECONOMY_SERVER. Main-thread only; no
// worker access to stage/member state. The patch module installs these calls.
void CompetitiveGBucksBegin(MMatchStage* stage);
void CompetitiveGBucksEnter(MMatchStage* stage, MMatchObject* player);
void CompetitiveGBucksLeave(MMatchStage* stage, MMatchObject* player);
void CompetitiveGBucksKill(MMatchStage* stage, MMatchObject* attacker, MMatchObject* victim);
void CompetitiveGBucksFinish(MMatchStage* stage);
void CompetitiveGBucksDestroy(MMatchStage* stage);
void CompetitiveGBucksTick(MMatchServer& server);
// Main server.cpp MUST implement this best-effort, server-only HUD notification
// (wire 49003: amount/int, completion as 0/1 int). It selects the current online CID,
// never credits BP. Called only after commit AND that session's wallet sync.
// completion=false: "+N GBucks" kill; true: completion bonus (optional UI).
void CompetitiveGBucksReward(int cid, int amount, bool completion);
// Backend scoreboard accessor: committed match kill GBucks, excludes bonus.
std::int64_t CompetitiveGBucksEarned(MMatchStage* stage, MMatchObject* player);