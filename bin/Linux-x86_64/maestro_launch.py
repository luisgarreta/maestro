import pymmlibs


def main():
    pymmlibs.mmerr_set_mmlibs()
    import startup
    startup.main()


if __name__ == "__main__":
    main()
