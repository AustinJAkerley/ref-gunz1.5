# The upstream project uses one unity unit per library (CPP_PER_UNITY=500).
# Preserve that build assumption instead of changing original gameplay includes.
foreach(target cml CSCommon SafeUDP RealSpace2 Mint2 Locator GunzCore MatchCore)
    set_target_properties(${target} PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 500)
    target_compile_options(${target} PRIVATE /EHsc /FI/baseline/compat/platform_headers.h)
endforeach()
target_compile_definitions(RealSpace2 PRIVATE _USE_GDIPLUS)
target_compile_options(Mint2 PRIVATE /FI/baseline/compat/mint_headers.h)
target_compile_options(GunzCore PRIVATE /FI/baseline/compat/game_headers.h)
target_include_directories(Locator PRIVATE ${S}/MatchServer)
add_library(reference_diagnostics STATIC ${CMAKE_CURRENT_LIST_DIR}/dxerr.cpp)
target_link_libraries(RealSpace2 PUBLIC reference_diagnostics)
target_sources(MatchCore PRIVATE ${S}/sdk/ini/ini.c)
# Use upstream's built-in direct SERVER0 list for this isolated local baseline.
# No external locator service is needed; authentication remains unchanged.
target_compile_options(GunzCore PRIVATE /U_LOCATOR)
target_compile_options(Gunz PRIVATE /U_LOCATOR)