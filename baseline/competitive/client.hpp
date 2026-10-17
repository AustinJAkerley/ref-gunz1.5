#pragma once
#include "MUID.h"
#include "MCommand.h"
#include "MBlobArray.h"
#include "wire.hpp"
#include "competitive.hpp"
#include "damage.hpp"
#include "MTime.h"
#include <map>
inline std::map<MUID,CompetitiveRatingWire>& CompetitiveClientRatings(){static std::map<MUID,CompetitiveRatingWire> values;return values;}
inline void CompetitiveReceive(MCommand* command){
    auto* parameter=command->GetParameter(0);if(!parameter||parameter->GetType()!=MPT_BLOB)return;
    void* blob=parameter->GetPointer();
    if(!MValidateBlobArraySize(blob,static_cast<MCmdParamBlob*>(parameter)->GetPayloadSize()))return;
    const int count=MGetBlobArrayCount(blob);
    if(count<0||count>64||MGetBlobArrayElementSize(blob)!=sizeof(CompetitiveRatingWire))return;
    std::map<MUID,CompetitiveRatingWire> next;
    for(int i=0;i<count;++i){
        CompetitiveRatingWire value;memcpy(&value,MGetBlobArrayElement(blob,i),sizeof(value));
        if(value.elo<0||value.rank<0||value.rank>5||value.position<0||value.wins<0||value.losses<0)return;
        next[MUID(value.uidHigh,value.uidLow)]=value;
    }
    CompetitiveClientRatings()=std::move(next);
}
inline std::string CompetitiveText(const MUID& uid){
    auto& values=CompetitiveClientRatings();auto it=values.find(uid);
    if(it==values.end())return "--";
    return std::to_string(it->second.elo)+" "+competitive::label(it->second.rank);
}
inline competitive::DamageConfirmation& CompetitiveDamage(){static competitive::DamageConfirmation value;return value;}
inline void CompetitiveHit(int amount,bool confirmed=false){CompetitiveDamage().add(amount,GetGlobalTimeMS(),confirmed);}
inline void CompetitiveClear(){CompetitiveClientRatings().clear();CompetitiveDamage().clear();}