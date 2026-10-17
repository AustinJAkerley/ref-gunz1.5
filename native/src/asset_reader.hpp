#pragma once
#include <cstdint>
#include <cmath>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace gz {
class AssetReader {
    std::vector<std::uint8_t> bytes;
    std::size_t position=0;
public:
    explicit AssetReader(const std::string& path) {
        std::ifstream file(path,std::ios::binary|std::ios::ate);
        if(!file) throw std::runtime_error("Missing converted asset: "+path);
        const auto size=file.tellg();
        if(size<0||size>256*1024*1024) throw std::runtime_error("Asset size limit");
        bytes.resize(static_cast<std::size_t>(size));file.seekg(0);
        if(!file.read(reinterpret_cast<char*>(bytes.data()),size)) throw std::runtime_error("Asset read failed");
    }
    std::uint32_t u() {
        if(position+4>bytes.size()) throw std::runtime_error("Truncated asset");
        std::uint32_t n=0;for(int i=0;i<4;++i) n|=std::uint32_t(bytes[position++])<<(8*i);return n;
    }
    std::uint32_t count(std::uint32_t limit) {auto n=u();if(n>limit) throw std::runtime_error("Asset count limit");return n;}
    float f() {
        auto bits=u();float value;std::memcpy(&value,&bits,4);
        if(!std::isfinite(value)||std::abs(value)>100000) throw std::runtime_error("Invalid asset coordinate");
        return value;
    }
    std::string text() {
        auto size=count(240);if(position+size>bytes.size()) throw std::runtime_error("Truncated asset name");
        std::string s(bytes.begin()+position,bytes.begin()+position+size);position+=size;
        if(s.empty()||s.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")!=std::string::npos||s.find("..")!=std::string::npos)
            throw std::runtime_error("Unsafe texture name");
        return s;
    }
    void end() {if(position!=bytes.size()) throw std::runtime_error("Trailing asset data");}
};
}