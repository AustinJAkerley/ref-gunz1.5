#pragma once
#include "world.hpp"
#include <cstddef>
#include <string>

namespace gz {
using Bytes=std::vector<std::uint8_t>;
enum class Kind : std::uint32_t { Welcome=1, Input=2, Snapshot=3 };
struct Message { Kind kind; std::uint32_t id=0; Input input; Snapshot snapshot; };
inline bool newer(std::uint32_t candidate,std::uint32_t previous) {
	const auto distance=candidate-previous;
	return distance!=0 && distance<0x80000000u;
}
Bytes encodeWelcome(std::uint32_t id);
Bytes encodeInput(const Input& input);
Bytes encodeSnapshot(const Snapshot& snapshot);
bool decode(const void* data,std::size_t size,Message& output);
} // namespace gz