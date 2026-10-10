/* Independently authored CT2Trainer. MIT; see licenses/CT2Trainer-MIT.txt. */
#ifndef CT2TRAINER_TARGET_BROKER_ABI_H
#define CT2TRAINER_TARGET_BROKER_ABI_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#define TF_BROKER_VERSION 1u
#define TF_BROKER_PAYLOAD 512u
#define TF_BROKER_MAX_REQUESTS 64u
#define TF_BROKER_HOLD 1u
#define TF_BROKER_WORKER_COMPLETE 0x100u
#define TF_BROKER_MAIN_COMPLETE 0x200u
#define TF_BROKER_TLS_CLEARED 0x400u
#define TF_CMD_HELLO 1u
#define TF_CMD_SUBMIT 2u
#define TF_CMD_QUERY 3u
#define TF_CMD_CANCEL 4u
#define TF_CMD_RELEASE 5u
#define TF_READY 1u
#define TF_PREPARED 2u
#define TF_RUNNING 3u
#define TF_DONE 4u
#define TF_CANCELLED 5u
#define TF_REFUSED 6u
#define TF_UNKNOWN 7u
#define TF_OP_CDECL_ADD 1u
#define TF_OP_STDCALL_ADD 2u
#define TF_OP_WIDE 3u
#define TF_OP_MIXED 4u
#define TF_OP_ECHO 5u
#define TF_OP_MAIN_BOOL 6u
#define TF_OP_WAIT_ADD 7u
#define TF_OP_WRONG_AFFINITY 8u
#pragma pack(push, 1)
typedef struct tf_broker_frame {
    char magic[4]; uint16_t version, size;
    uint32_t command, status, operation, flags;
    uint64_t request_id, generation;
    uint32_t owner_pid, target_pid;
    uint64_t owner_created, target_created;
    uint8_t nonce[16];
    uint64_t deadline_qpc, qpc_frequency;
    uint32_t thread_id, main_thread_id;
    uint64_t thread_created, call_count;
    uint32_t payload_size, error;
    uint64_t clock_sample;
    uint32_t result_kind, pointer_bits;
    uint64_t tls_marker;
    uint8_t payload[TF_BROKER_PAYLOAD];
} tf_broker_frame;
#pragma pack(pop)
typedef char tf_frame_size_check[(sizeof(tf_broker_frame) == 664) ? 1 : -1];
typedef struct tf_broker_stats {
    uint32_t version, size, requests, worker_handles, live_workers, cancelled, owner_alive, pointer_bits;
    uint64_t calls;
} tf_broker_stats;
/* Host calls Start and Pump only on its captured main thread. No DllMain work. */
/* A trusted preloaded host registers its fixed typed dispatcher, never a wire pointer. */
typedef uint32_t (__cdecl *tf_broker_dispatch_fn)(const tf_broker_frame *, tf_broker_frame *, HANDLE, HANDLE, uint32_t);
typedef int (__cdecl *tf_broker_start_fn)(uint32_t, uint64_t, const uint8_t[16], tf_broker_dispatch_fn);
typedef void (__cdecl *tf_broker_pump_fn)(void);
typedef int (__cdecl *tf_broker_inspect_fn)(tf_broker_stats *);
#ifdef TF_BROKER_BUILD
__declspec(dllexport) int __cdecl TFBrokerStart(uint32_t owner, uint64_t created, const uint8_t nonce[16], tf_broker_dispatch_fn dispatch);
__declspec(dllexport) void __cdecl TFBrokerPumpMain(void);
__declspec(dllexport) int __cdecl TFBrokerInspect(tf_broker_stats *stats);
#endif
#endif
