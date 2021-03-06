from fffi import FortranLibrary
from cffi import FFI

lib = FortranLibrary('test_strings')
lib.fdef("""
    subroutine test0
    end subroutine test0

    subroutine test_string(s)
        character(len=*), intent(in) :: s
    end subroutine test_string
""")

#lib.compile(verbose=True)
lib.load()
print(lib.csource)


print(dir(lib._lib))
lib.test0()
lib.test_string('Hello, Fortran!')
