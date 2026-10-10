// Independently owned Mono fixture. MIT: CT2Trainer license.
using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
namespace CT2TrainerOwned {
 public sealed class Counter {
  public int Value;
  public Counter(int value) { Value=value; }
  [MethodImpl(MethodImplOptions.NoInlining)] public int GetCurrentStatus() { return Value; }
 }
 public static class Application {
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  static uint main;
  static bool flag;
  public static int Calls;
  public static void Initialize() { main=GetCurrentThreadId(); }
  [MethodImpl(MethodImplOptions.NoInlining)] public static void set_runInBackground(bool value) {
   if (GetCurrentThreadId()!=main) throw new InvalidOperationException("Owned main-thread affinity");
   flag=value; ++Calls;
  }
  [MethodImpl(MethodImplOptions.NoInlining)] public static int GetCurrentStatus() { return flag?19:17; }
  [MethodImpl(MethodImplOptions.NoInlining)] public static int Add(int value) { return value+3; }
  [MethodImpl(MethodImplOptions.NoInlining)] public static int Add(bool value) { return value?101:103; }
  public static void Ambiguous<T>() {}
  public static void Ambiguous<T,U>() {}
  public static void SingleGeneric<T>() { ++Calls; }
  public static void RefBoolean(ref bool value) { value=false; ++Calls; }
  public static void Varargs(__arglist) { ++Calls; }
  public static Counter CreateCounter() { return new Counter(41); }
  public static void ThrowAfterIncrement() { ++Calls; throw new InvalidOperationException("Owned partial effect"); }
  public static int CallCount() { return Calls; }
  [MethodImpl(MethodImplOptions.NoInlining)] public static int WaitThenIncrement(bool wait) {
   if (wait) System.Threading.Thread.Sleep(200);
   return ++Calls;
  }
  public static void Collect() { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); }
 }
}
