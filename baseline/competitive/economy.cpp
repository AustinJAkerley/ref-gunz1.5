#ifdef GUNZ_ECONOMY_SERVER
#include "stdafx.h"
#endif
#include "economy.hpp"
#include "sqlite3.h"
#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace competitive { namespace economy {
namespace {
void exec(sqlite3* db, const char* sql) {
    char* error = nullptr;
    if (sqlite3_exec(db, sql, nullptr, nullptr, &error) != SQLITE_OK) {
        const std::string message = error ? error : sqlite3_errmsg(db);
        sqlite3_free(error);
        throw std::runtime_error(message);
    }
}
class Statement {
    sqlite3* db_;
    sqlite3_stmt* stmt_ = nullptr;
public:
    Statement(sqlite3* db, const char* sql) : db_(db) {
        if (sqlite3_prepare_v2(db, sql, -1, &stmt_, nullptr) != SQLITE_OK) {
            sqlite3_finalize(stmt_);
            throw std::runtime_error(sqlite3_errmsg(db));
        }
    }
    Statement(const Statement&) = delete;
    Statement& operator=(const Statement&) = delete;
    ~Statement() { sqlite3_finalize(stmt_); }
    void bind(int at, std::int64_t value) {
        if (sqlite3_bind_int64(stmt_, at, value) != SQLITE_OK)
            throw std::runtime_error(sqlite3_errmsg(db_));
    }
    void bind(int at, const std::string& value) {
        if (sqlite3_bind_text(stmt_, at, value.c_str(), int(value.size()), SQLITE_TRANSIENT) != SQLITE_OK)
            throw std::runtime_error(sqlite3_errmsg(db_));
    }
    bool step() {
        const int rc = sqlite3_step(stmt_);
        if (rc != SQLITE_ROW && rc != SQLITE_DONE) throw std::runtime_error(sqlite3_errmsg(db_));
        return rc == SQLITE_ROW;
    }
    std::int64_t number(int col) const { return sqlite3_column_int64(stmt_, col); }
    std::string text(int col) const {
        const auto* value = sqlite3_column_text(stmt_, col);
        return value ? reinterpret_cast<const char*>(value) : "";
    }
};
class Transaction {
    sqlite3* db_;
    bool committed_ = false;
public:
    explicit Transaction(sqlite3* db) : db_(db) { exec(db_, "BEGIN IMMEDIATE"); }
    Transaction(const Transaction&) = delete;
    ~Transaction() { if (!committed_) sqlite3_exec(db_, "ROLLBACK", nullptr, nullptr, nullptr); }
    void commit() { exec(db_, "COMMIT"); committed_ = true; }
};
bool human(const Player& p) { return p.cid > 0 && p.aid > 0 && !p.bot; }
void validate(const Event& e) {
    if (e.id.empty() || e.id.size() > 240 || e.match.empty() || e.match.size() > 180 ||
        int(e.kind) < int(Kind::Begin) || int(e.kind) > int(Kind::Close))
        throw std::runtime_error("Invalid GBucks event");
}
void bindEvent(Statement& q, const Event& e) {
    q.bind(1, e.id); q.bind(2, e.match); q.bind(3, int(e.kind));
    q.bind(4, e.cid); q.bind(5, e.aid); q.bind(6, e.victim);
    q.bind(7, e.victimAid); q.bind(8, e.amount);
}
Event readEvent(const Statement& q) {
    return {q.text(0), q.text(1), Kind(q.number(2)), int(q.number(3)), int(q.number(4)),
        int(q.number(5)), int(q.number(6)), int(q.number(7))};
}
bool characterIdentity(sqlite3* db, int cid, int aid) {
    if (cid <= 0 || aid <= 0) return false;
    // DeleteCharacter retains CID/AID. A queued Join must still establish its
    // event-time identity after soft deletion, but cannot invent an association.
    Statement q(db, "SELECT 1 FROM Character WHERE CID=? AND AID=?");
    q.bind(1, cid); q.bind(2, aid); return q.step();
}
bool activeCharacter(sqlite3* db, int cid, int aid) {
    if (cid <= 0 || aid <= 0) return false;
    Statement q(db, "SELECT 1 FROM Character WHERE CID=? AND AID=? AND COALESCE(DeleteFlag,0)=0");
    q.bind(1, cid); q.bind(2, aid); return q.step();
}
bool member(sqlite3* db, const Event& e, int cid, int aid) {
    Statement q(db, "SELECT 1 FROM GBucksParticipant WHERE MatchID=? AND CID=? AND AID=? AND Finished=0");
    q.bind(1, e.match); q.bind(2, cid); q.bind(3, aid); return q.step();
}
void credit(sqlite3* db, int cid, std::int64_t amount) {
    if (amount == 0) return;
    if (amount < 0 || amount > (std::numeric_limits<int>::max)())
        throw std::runtime_error("GBucks award exceeds wallet representation");
    Statement q(db, "UPDATE Character SET BP=BP+? WHERE CID=? AND BP>=0 AND BP<=2147483647-?");
    q.bind(1, amount); q.bind(2, cid); q.bind(3, amount); q.step();
    if (sqlite3_changes(db) != 1) throw std::runtime_error("GBucks wallet unavailable or full; retry after spending");
    Statement init(db, "INSERT OR IGNORE INTO GBucksWallet(CID,Total) VALUES(?,0)");
    init.bind(1, cid); init.step();
    Statement total(db, "UPDATE GBucksWallet SET Total=Total+? WHERE CID=? AND Total<=9223372036854775807-?");
    total.bind(1, amount); total.bind(2, cid); total.bind(3, amount); total.step();
    if (sqlite3_changes(db) != 1) throw std::runtime_error("GBucks total overflow");
}
}

bool eligible(const Kill& k) {
    const auto& a = k.attacker; const auto& v = k.victim;
    return k.playing && k.allowedMode && k.sameStage && k.victimAlive && k.activeDuelPair &&
        human(a) && human(v) && a.inBattle && v.inBattle && !a.spectator && !v.spectator &&
        a.cid != v.cid && a.aid != v.aid && (!k.teamGame || a.team != v.team);
}
int killReward(int attackerElo, int victimElo) {
    // Equivalent to round(10 + 10 / (1 + 10^((attacker-victim)/400))).
    // Subtract as doubles, and use a nonpositive exponent to avoid overflow
    // even for the full int range. Higher-rated victims are worth more.
    const double difference = double(attackerElo) - double(victimElo);
    const double ratio = std::pow(10.0, -std::abs(difference) / 400.0);
    const double expected = difference >= 0 ? ratio / (1.0 + ratio) : 1.0 / (1.0 + ratio);
    return (std::max)(10, (std::min)(20, int(std::round(10.0 + 10.0 * expected))));
}
int killReward(sqlite3* db, int attackerCID, int victimCID) {
    Statement q(db, "SELECT COALESCE((SELECT Elo FROM DuelRating WHERE CID=?),1000),"
                    "COALESCE((SELECT Elo FROM DuelRating WHERE CID=?),1000)");
    q.bind(1, attackerCID); q.bind(2, victimCID);
    if (!q.step()) throw std::runtime_error("Missing GBucks Elo snapshot");
    return killReward(int(q.number(0)), int(q.number(1)));
}
bool operator==(const Event& a, const Event& b) {
    return a.id == b.id && a.match == b.match && a.kind == b.kind && a.cid == b.cid &&
        a.aid == b.aid && a.victim == b.victim && a.victimAid == b.victimAid && a.amount == b.amount;
}
Event Match::event(Kind kind, int cid, int aid) {
    return {id_ + ":" + std::to_string(++sequence_), id_, kind, cid, aid, 0, 0, 0};
}
std::vector<Event> Match::begin(const std::string& id) {
    if (!closed_) throw std::runtime_error("GBucks match already running");
    if (id.empty() || id.size() > 180) throw std::runtime_error("Invalid GBucks match ID");
    id_ = id; sequence_ = 0; closed_ = false; members_.clear();
    return {event(Kind::Begin)};
}
std::vector<Event> Match::join(const Player& p) {
    if (closed_ || !human(p) || members_.count(p.cid)) return {};
    members_.emplace(p.cid, Member{p.aid, false});
    return {event(Kind::Join, p.cid, p.aid)};
}
std::vector<Event> Match::leave(const Player& p) {
    if (closed_ || !human(p)) return {};
    auto events = join(p); // Even leaving while loading disqualifies a later reconnect.
    auto& m = members_.at(p.cid);
    if (!m.left && m.aid == p.aid) { m.left = true; events.push_back(event(Kind::Leave, p.cid, p.aid)); }
    return events;
}
std::vector<Event> Match::kill(const Kill& k) {
    if (closed_ || !eligible(k)) return {};
    const auto a = members_.find(k.attacker.cid), v = members_.find(k.victim.cid);
    if (a == members_.end() || v == members_.end() ||
        a->second.aid != k.attacker.aid || v->second.aid != k.victim.aid) return {};
    auto e = event(Kind::Kill, k.attacker.cid, k.attacker.aid);
    e.victim = k.victim.cid; e.victimAid = k.victim.aid;
    return {e};
}
std::vector<Event> Match::finish(const std::vector<Player>& remaining) {
    if (closed_) return {};
    std::vector<Event> events;
    for (const auto& p : remaining) {
        const auto it = members_.find(p.cid);
        if (human(p) && p.inBattle && !p.spectator && it != members_.end() &&
            it->second.aid == p.aid && !it->second.left)
            events.push_back(event(Kind::Finish, p.cid, p.aid));
    }
    events.push_back(event(Kind::Close)); closed_ = true;
    return events;
}
std::vector<Event> Match::abort() { return finish({}); }

void RewardNotifications::committed(const Event& e, const Result& result, std::uint64_t session) {
    if (session && result.applied && !result.replay && result.credited > 0 &&
        (e.kind == Kind::Kill || e.kind == Kind::Finish))
        pending_.emplace(e.id, RewardNotification{e.cid, result.credited, e.kind == Kind::Finish, session});
}
std::vector<RewardNotification> RewardNotifications::take(const std::map<int, std::uint64_t>& online,
                                                         const std::set<int>& walletsReady) {
    std::vector<RewardNotification> ready;
    for (auto it = pending_.begin(); it != pending_.end();) {
        const auto session = online.find(it->second.cid);
        if (session == online.end() || session->second != it->second.session) {
            it = pending_.erase(it);
        } else if (walletsReady.count(it->second.cid)) {
            ready.push_back(it->second); it = pending_.erase(it);
        } else ++it;
    }
    return ready;
}

void initialize(sqlite3* db) {
    Transaction t(db);
    exec(db, "CREATE TABLE IF NOT EXISTS GBucksWallet(CID INTEGER PRIMARY KEY,Total INTEGER NOT NULL DEFAULT 0 CHECK(Total>=0))");
    exec(db, "CREATE TABLE IF NOT EXISTS GBucksMatch(MatchID TEXT PRIMARY KEY,Closed INTEGER NOT NULL DEFAULT 0)");
    exec(db, "CREATE TABLE IF NOT EXISTS GBucksParticipant(MatchID TEXT NOT NULL,CID INTEGER NOT NULL,AID INTEGER NOT NULL,LeftEarly INTEGER NOT NULL DEFAULT 0,Finished INTEGER NOT NULL DEFAULT 0,KillEarned INTEGER NOT NULL DEFAULT 0,Bonus INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(MatchID,CID))");
    exec(db, "CREATE TABLE IF NOT EXISTS GBucksEvent(EventID TEXT PRIMARY KEY,MatchID TEXT NOT NULL,Kind INTEGER NOT NULL,CID INTEGER NOT NULL,AID INTEGER NOT NULL,VictimCID INTEGER NOT NULL,VictimAID INTEGER NOT NULL,Amount INTEGER NOT NULL,Credited INTEGER NOT NULL DEFAULT 0,CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)");
    t.commit();
}
Result record(sqlite3* db, const Event& e) {
    validate(e);
    Transaction t(db);
    {
        Statement q(db, "SELECT EventID,MatchID,Kind,CID,AID,VictimCID,VictimAID,Amount FROM GBucksEvent WHERE EventID=?");
        q.bind(1, e.id);
        if (q.step()) {
            if (!(readEvent(q) == e)) throw std::runtime_error("GBucks event ID collision");
            t.commit(); return {false, true, 0};
        }
    }
    {
        Statement q(db, "INSERT INTO GBucksEvent(EventID,MatchID,Kind,CID,AID,VictimCID,VictimAID,Amount) VALUES(?,?,?,?,?,?,?,?)");
        bindEvent(q, e); q.step();
    }
    bool open = false;
    {
        Statement q(db, "SELECT Closed FROM GBucksMatch WHERE MatchID=?");
        q.bind(1, e.match); open = q.step() && q.number(0) == 0;
    }
    Result result;
    if (e.kind == Kind::Begin) {
        Statement q(db, "INSERT OR IGNORE INTO GBucksMatch(MatchID) VALUES(?)");
        q.bind(1, e.match); q.step(); result.applied = sqlite3_changes(db) == 1;
    } else if (open && e.kind == Kind::Close) {
        Statement q(db, "UPDATE GBucksMatch SET Closed=1 WHERE MatchID=?");
        q.bind(1, e.match); q.step(); result.applied = true;
    } else if (open && e.kind == Kind::Join) {
        if (characterIdentity(db, e.cid, e.aid)) {
            Statement q(db, "INSERT OR IGNORE INTO GBucksParticipant(MatchID,CID,AID) VALUES(?,?,?)");
            q.bind(1, e.match); q.bind(2, e.cid); q.bind(3, e.aid); q.step();
            result.applied = sqlite3_changes(db) == 1;
        }
    } else if (open && activeCharacter(db, e.cid, e.aid) && member(db, e, e.cid, e.aid)) {
        if (e.kind == Kind::Leave) {
            Statement q(db, "UPDATE GBucksParticipant SET LeftEarly=1 WHERE MatchID=? AND CID=?");
            q.bind(1, e.match); q.bind(2, e.cid); q.step(); result.applied = true;
        } else if (e.kind == Kind::Kill && (e.amount == 0 || (e.amount >= 10 && e.amount <= 15)) &&
            e.cid != e.victim && e.aid != e.victimAid && member(db, e, e.victim, e.victimAid)) {
            // The ordered durable Join preserves the accepted victim identity.
            // Later deletion cannot revoke this kill; only its payee must still
            // be active. Live kill eligibility was checked before journaling.
            // New events read Elo only here, under the same writer transaction
            // as the wallet and ledger. SQL contention rolls back and retains
            // the journal head. Legacy already-journaled 10..15 amounts remain
            // fixed; Match::kill never generates those payloads anymore.
            const int amount = e.amount == 0 ? killReward(db, e.cid, e.victim) : e.amount;
            credit(db, e.cid, amount);
            Statement q(db, "UPDATE GBucksParticipant SET KillEarned=KillEarned+? WHERE MatchID=? AND CID=?");
            q.bind(1, amount); q.bind(2, e.match); q.bind(3, e.cid); q.step();
            result = {true, false, amount};
        } else if (e.kind == Kind::Finish) {
            std::int64_t bonus = 0;
            {
                Statement q(db, "SELECT CASE WHEN LeftEarly=0 THEN KillEarned/2 ELSE 0 END FROM GBucksParticipant WHERE MatchID=? AND CID=?");
                q.bind(1, e.match); q.bind(2, e.cid); q.step(); bonus = q.number(0);
            }
            credit(db, e.cid, bonus);
            Statement q(db, "UPDATE GBucksParticipant SET Finished=1,Bonus=? WHERE MatchID=? AND CID=?");
            q.bind(1, bonus); q.bind(2, e.match); q.bind(3, e.cid); q.step();
            result = {true, false, int(bonus)};
        }
    }
    {
        Statement q(db, "UPDATE GBucksEvent SET Credited=? WHERE EventID=?");
        q.bind(1, result.credited); q.bind(2, e.id); q.step();
    }
    t.commit(); return result;
}
std::int64_t rewardTotal(sqlite3* db, int cid) {
    Statement q(db, "SELECT Total FROM GBucksWallet WHERE CID=?");
    q.bind(1, cid); return q.step() ? q.number(0) : 0;
}
std::int64_t earned(sqlite3* db, const std::string& match, int cid) {
    Statement q(db, "SELECT KillEarned FROM GBucksParticipant WHERE MatchID=? AND CID=?");
    q.bind(1, match); q.bind(2, cid); return q.step() ? q.number(0) : 0;
}
void initializeJournal(sqlite3* db) {
    exec(db, "PRAGMA synchronous=FULL");
    exec(db, "CREATE TABLE IF NOT EXISTS PendingGBucks(Sequence INTEGER PRIMARY KEY AUTOINCREMENT,EventID TEXT NOT NULL UNIQUE,MatchID TEXT NOT NULL,Kind INTEGER NOT NULL,CID INTEGER NOT NULL,AID INTEGER NOT NULL,VictimCID INTEGER NOT NULL,VictimAID INTEGER NOT NULL,Amount INTEGER NOT NULL)");
}
void enqueue(sqlite3* db, const Event& e) {
    validate(e);
    Transaction t(db);
    {
        Statement q(db, "INSERT OR IGNORE INTO PendingGBucks(EventID,MatchID,Kind,CID,AID,VictimCID,VictimAID,Amount) VALUES(?,?,?,?,?,?,?,?)");
        bindEvent(q, e); q.step();
    }
    Statement q(db, "SELECT EventID,MatchID,Kind,CID,AID,VictimCID,VictimAID,Amount FROM PendingGBucks WHERE EventID=?");
    q.bind(1, e.id);
    if (!q.step() || !(readEvent(q) == e)) throw std::runtime_error("GBucks journal event ID collision");
    t.commit();
}
bool oldest(sqlite3* db, Event& e) {
    Statement q(db, "SELECT EventID,MatchID,Kind,CID,AID,VictimCID,VictimAID,Amount FROM PendingGBucks ORDER BY Sequence LIMIT 1");
    if (!q.step()) return false;
    e = readEvent(q); return true;
}
void acknowledge(sqlite3* db, const std::string& id) {
    Statement q(db, "DELETE FROM PendingGBucks WHERE EventID=?"); q.bind(1, id); q.step();
}
bool syncWallet(int& bp, long long& loadedTotal, std::int64_t total) {
    if (total < loadedTotal || loadedTotal < 0) throw std::runtime_error("GBucks reward watermark regressed");
    const auto delta = total - loadedTotal;
    if (!delta) return false;
    if (delta > std::int64_t((std::numeric_limits<int>::max)()) - bp)
        throw std::runtime_error("GBucks live wallet overflow");
    bp = int(std::int64_t(bp) + delta); loadedTotal = total;
    return true;
}
} }

#ifdef GUNZ_ECONOMY_SERVER
#include "server.hpp"
#include "MMatchServer.h"
#include "MMatchStage.h"
#include "MMatchRuleDuel.h"
#include "MTime.h"

namespace gbucks_adapter {
namespace ec = competitive::economy;
// Separate zero-busy-timeout connections, like the existing Elo outbox.
// Only this main-thread adapter opens these paths; tests use disposable DBs.
class Connection {
    sqlite3* db_ = nullptr;
public:
    Connection(const char* path, bool journal) {
        const int flags = SQLITE_OPEN_READWRITE | (journal ? SQLITE_OPEN_CREATE : 0);
        if (sqlite3_open_v2(path, &db_, flags, nullptr) != SQLITE_OK) {
            sqlite3_close(db_); throw std::runtime_error("Cannot open GBucks database");
        }
        try {
            sqlite3_busy_timeout(db_, 0);
            if (journal) ec::initializeJournal(db_);
        } catch (...) { sqlite3_close(db_); throw; }
    }
    ~Connection() { sqlite3_close(db_); }
    sqlite3* get() const { return db_; }
};
sqlite3* gameDB() { static Connection c("GunzDB.sq3", false); return c.get(); }
sqlite3* journalDB() { static Connection c("GBucksPending.sq3", true); return c.get(); }
std::map<MMatchStage*, ec::Match> matches;
std::deque<ec::Event> pending;
std::set<int> walletNotifications;
ec::RewardNotifications rewardNotifications;
std::uint64_t session(MMatchObject* p) {
    const auto uid = p->GetUID();
    return (std::uint64_t(std::uint32_t(uid.High)) << 32) | std::uint32_t(uid.Low);
}
std::uint64_t onlineSession(MMatchServer& server, int cid) {
    for (const auto& item : *server.GetObjects()) {
        auto* p = item.second;
        if (p && p->GetCharInfo() && !(p->GetPlayerFlags() & MTD_PlayerFlags_Bot) &&
            int(p->GetCharInfo()->m_nCID) == cid) return session(p);
    }
    return 0;
}
ec::Player player(MMatchObject* p) {
    if (!p || !p->GetCharInfo()) return {};
    return {int(p->GetCharInfo()->m_nCID), int(p->GetAccountInfo()->m_nAID), int(p->GetTeam()),
        (p->GetPlayerFlags() & MTD_PlayerFlags_Bot) != 0,
        p->GetTeam() == MMT_SPECTATOR || (p->GetPlayerFlags() & MTD_PlayerFlags_AdminHide) != 0,
        p->GetEnterBattle()};
}
void submit(std::vector<ec::Event> events) {
    for (auto& e : events) pending.push_back(std::move(e));
}
void flush(MMatchServer& server) {
    // Persist new events before touching the contended game DB. A failure at
    // either boundary leaves the head intact; replay after commit is harmless.
    try {
        auto* journal = journalDB();
        while (!pending.empty()) {
            ec::enqueue(journal, pending.front()); pending.pop_front();
        }
        ec::Event e;
        for (int i = 0; i < 32 && ec::oldest(journal, e); ++i) {
            const auto result = ec::record(gameDB(), e); // Returns only after COMMIT.
            // Queue BEFORE ACK: an ACK failure must not lose this notification.
            // A replay returns applied=false/credited=0 and cannot requeue it.
            // Notification failures must never prevent the durable journal ACK.
            try {
                if (result.applied && result.credited > 0)
                    rewardNotifications.committed(e, result, onlineSession(server, e.cid));
            } catch (...) { MLog("GBucks committed; HUD notification unavailable\n"); }
            ec::acknowledge(journal, e.id);
        }
    } catch (const std::exception& e) {
        MLog("GBucks events retained for retry: %s\n", e.what());
    }
}
void sync(MMatchServer& server) {
    std::map<int, std::uint64_t> online;
    std::set<int> ready;
    for (const auto& item : *server.GetObjects()) {
        auto* p = item.second;
        if (!p || !p->GetCharInfo() || (p->GetPlayerFlags() & MTD_PlayerFlags_Bot)) continue;
        auto& c = *p->GetCharInfo();
        if (!c.m_nCID) continue;
        online.emplace(int(c.m_nCID), session(p));
        try {
            if (c.m_nCID && ec::syncWallet(c.m_nBP, c.m_nGBucksApplied, ec::rewardTotal(gameDB(), int(c.m_nCID))))
                walletNotifications.insert(int(c.m_nCID));
            // Char info may arrive before its inventory has loaded. Do not
            // trigger synchronous inventory DB reads on every kill, nor lose
            // the notification if item loading is temporarily unavailable.
            if (walletNotifications.count(int(c.m_nCID)) && c.m_ItemList.IsDoneDbAccess()) {
                server.CompetitiveGBucksWallet(p->GetUID());
                walletNotifications.erase(int(c.m_nCID));
            }
            if (c.m_ItemList.IsDoneDbAccess() && !walletNotifications.count(int(c.m_nCID)))
                ready.insert(int(c.m_nCID));
        } catch (const std::exception& e) { MLog("GBucks wallet sync will retry: %s\n", e.what()); }
    }
    // Only this session's already-synchronized wallets can show a popup. The
    // queue consumes notices before calling main; failed sends are not retried.
    for (const auto& n : rewardNotifications.take(online, ready)) {
        try { CompetitiveGBucksReward(n.cid, n.amount, n.completion); }
        catch (...) { MLog("GBucks committed; HUD notification send failed\n"); }
    }
}
void flushAndSync() { auto& server = *MGetMatchServer(); flush(server); sync(server); }
}
void CompetitiveGBucksBegin(MMatchStage* stage) {
    using namespace gbucks_adapter;
    auto& match = matches[stage];
    submit(match.abort());
    submit(match.begin(CompetitiveRoundID(stage->GetUID(), -1)));
    for (auto it = stage->GetObjBegin(); it != stage->GetObjEnd(); ++it) submit(match.join(player(it->second)));
    flushAndSync();
}
void CompetitiveGBucksEnter(MMatchStage* stage, MMatchObject* p) {
    using namespace gbucks_adapter;
    auto it = matches.find(stage);
    if (it != matches.end()) { submit(it->second.join(player(p))); flushAndSync(); }
}
void CompetitiveGBucksLeave(MMatchStage* stage, MMatchObject* p) {
    using namespace gbucks_adapter;
    auto it = matches.find(stage);
    if (it != matches.end()) { submit(it->second.leave(player(p))); flushAndSync(); }
}
void CompetitiveGBucksKill(MMatchStage* stage, MMatchObject* attacker, MMatchObject* victim) {
    using namespace gbucks_adapter;
    auto it = matches.find(stage);
    if (it == matches.end() || !attacker || !victim || !stage->GetRule()) return;
    ec::Kill k;
    k.attacker = player(attacker); k.victim = player(victim);
    k.playing = stage->GetState() == STAGE_STATE_RUN && stage->GetRule()->GetRoundState() == MMATCH_ROUNDSTATE_PLAY;
    k.sameStage = stage->GetObj(attacker->GetUID()) == attacker && stage->GetObj(victim->GetUID()) == victim &&
        attacker->GetStageUID() == stage->GetUID() && victim->GetStageUID() == stage->GetUID();
    k.victimAlive = victim->CheckAlive(); k.teamGame = stage->GetStageSetting()->IsTeamPlay();
    const auto type = stage->GetStageSetting()->GetGameType();
    k.allowedMode = type != MMATCH_GAMETYPE_TRAINING && type != MMATCH_GAMETYPE_SKILLMAP && !MGetGameTypeMgr()->IsQuestDerived(type);
    if (type == MMATCH_GAMETYPE_DUEL) {
        const auto* duel = static_cast<MMatchRuleDuel*>(stage->GetRule());
        k.activeDuelPair = (attacker->GetUID() == duel->uidChampion && victim->GetUID() == duel->uidChallenger) ||
            (attacker->GetUID() == duel->uidChallenger && victim->GetUID() == duel->uidChampion);
    }
    if (!ec::eligible(k)) return;
    submit(it->second.kill(k));
    flushAndSync();
}
void CompetitiveGBucksFinish(MMatchStage* stage) {
    using namespace gbucks_adapter;
    auto it = matches.find(stage); if (it == matches.end()) return;
    std::vector<ec::Player> remaining;
    for (auto p = stage->GetObjBegin(); p != stage->GetObjEnd(); ++p) remaining.push_back(player(p->second));
    submit(it->second.finish(remaining)); flushAndSync();
}
void CompetitiveGBucksDestroy(MMatchStage* stage) {
    using namespace gbucks_adapter;
    auto it = matches.find(stage); if (it == matches.end()) return;
    submit(it->second.abort()); matches.erase(it); flushAndSync();
}
void CompetitiveGBucksTick(MMatchServer& server) {
    static unsigned long long last = 0;
    const auto now = GetGlobalTimeMS(); if (now - last < 250) return; last = now;
    gbucks_adapter::flush(server); gbucks_adapter::sync(server);
}
std::int64_t CompetitiveGBucksEarned(MMatchStage* stage, MMatchObject* p) {
    const auto it = gbucks_adapter::matches.find(stage);
    if (it == gbucks_adapter::matches.end() || !p || !p->GetCharInfo()) return 0;
    try { return competitive::economy::earned(gbucks_adapter::gameDB(), it->second.id(), int(p->GetCharInfo()->m_nCID)); }
    catch (const std::exception&) { return 0; }
}
#endif