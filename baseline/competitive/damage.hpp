#pragma once
#include <cstdint>
#include <algorithm>

namespace competitive {
// One locally computed total per shot, or combined server receipts for targets
// damaged in the same shot tick. No misses, zero hits, or indefinite stale markers.
struct DamageConfirmation {
    int amount=0;
    std::uint64_t at=0;
    bool serverConfirmed=false;
    void add(int damage,std::uint64_t now,bool confirmed){
        if(damage<=0||damage>10000)return;
        const bool combine=confirmed&&serverConfirmed&&amount>0&&now>=at&&now-at<=50;
        amount=combine?std::min(10000,amount+damage):damage;
        at=now;serverConfirmed=confirmed;
    }
    bool visible(std::uint64_t now)const{return amount>0&&now>=at&&now-at<650;}
    void clear(){amount=0;at=0;serverConfirmed=false;}
};
}